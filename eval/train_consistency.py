"""Train and calibrate the caption–image consistency classifier on NewsCLIPpings.

Data: NewsCLIPpings merged_balanced split (Luo et al., 2021), precomputed CLIP ViT-B/32 image and
text embeddings released by the authors (Apache-2.0, huggingface.co/g-luo/news-clippings).
  train -> fit the logistic regression
  val   -> choose regularisation and the two decision thresholds
  test  -> in-distribution test metrics (reported, never used for tuning)
VERITE is NOT used here (see eval_consistency_verite.py).

Labels supported: pristine (match) vs falsified (mismatch). Nothing here teaches the model about
dates, places or out-of-context reuse of genuine images.

Usage:  python -I eval/train_consistency.py external/newsclippings
Output: models/consistency_classifier.json, eval/results/consistency_newsclippings.json
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, roc_auc_score

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "eval")]
import safe_pickle  # noqa: E402
from saqrsight.analysis.consistency import features  # noqa: E402

TARGET_PRECISION = 0.85   # each decisive label must be at least this precise on val


def load_split(root: Path, split: str):
    ann = json.load(open(root / "data/merged_balanced" / f"{split}.json"))["annotations"]
    img = safe_pickle.load(root / "embeddings" / f"clip_image_embeddings_{split}.pkl")
    txt = safe_pickle.load(root / "embeddings" / f"clip_text_embeddings_{split}.pkl")
    rows = [a for a in ann if a["image_id"] in img and a["id"] in txt]
    I = np.stack([np.asarray(img[a["image_id"]], dtype=np.float32).ravel() for a in rows])
    T = np.stack([np.asarray(txt[a["id"]], dtype=np.float32).ravel() for a in rows])
    y = np.array([0 if a["falsified"] else 1 for a in rows])  # 1 = caption matches image
    print(f"{split}: {len(rows)} of {len(ann)} pairs with embeddings, match share {y.mean():.3f}")
    return features(I, T), y


def metrics(y, p, t=0.5):
    pred = (p >= t).astype(int)
    pr, rc, f1, sup = precision_recall_fscore_support(y, pred, labels=[1, 0], zero_division=0)
    return {"accuracy": round(accuracy_score(y, pred), 4), "auc": round(roc_auc_score(y, p), 4),
            "match": {"precision": round(pr[0], 4), "recall": round(rc[0], 4), "f1": round(f1[0], 4), "n": int(sup[0])},
            "mismatch": {"precision": round(pr[1], 4), "recall": round(rc[1], 4), "f1": round(f1[1], 4), "n": int(sup[1])}}


def three_way(y, p, hi, lo):
    agree, disagree = p >= hi, p <= lo
    return {"agree_precision": round(float(y[agree].mean()), 4) if agree.any() else None,
            "disagree_precision": round(float(1 - y[disagree].mean()), 4) if disagree.any() else None,
            "coverage": round(float((agree | disagree).mean()), 4),
            "agree_share": round(float(agree.mean()), 4), "disagree_share": round(float(disagree.mean()), 4)}


def pick_thresholds(y, p):
    grid = np.round(np.arange(0.50, 0.99, 0.01), 2)
    hi = next((t for t in grid if (p >= t).any() and y[p >= t].mean() >= TARGET_PRECISION), 0.9)
    lo = next((t for t in np.round(1 - grid, 2) if (p <= t).any() and 1 - y[p <= t].mean() >= TARGET_PRECISION), 0.1)
    return float(hi), float(lo)


def main(root: Path):
    Xtr, ytr = load_split(root, "train")
    Xva, yva = load_split(root, "val")
    Xte, yte = load_split(root, "test")
    mean, scale = Xtr.mean(0), Xtr.std(0) + 1e-6
    z = lambda X: (X - mean) / scale  # noqa: E731
    best = None
    for C in (0.01, 0.1, 1.0):
        clf = LogisticRegression(C=C, max_iter=2000).fit(z(Xtr), ytr)
        auc = roc_auc_score(yva, clf.predict_proba(z(Xva))[:, 1])
        print(f"C={C}: val AUC {auc:.4f}")
        if best is None or auc > best[0]:
            best = (auc, C, clf)
    _, C, clf = best
    pva, pte = clf.predict_proba(z(Xva))[:, 1], clf.predict_proba(z(Xte))[:, 1]
    hi, lo = pick_thresholds(yva, pva)
    result = {"dataset": "NewsCLIPpings merged_balanced", "C": C, "thresholds": {"agree": hi, "disagree": lo},
              "val": metrics(yva, pva) | {"three_way": three_way(yva, pva, hi, lo)},
              "test": metrics(yte, pte) | {"three_way": three_way(yte, pte, hi, lo)},
              "sizes": {"train": len(ytr), "val": len(yva), "test": len(yte)}}
    out = ROOT / "models" / "consistency_classifier.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({
        "version": "nc-logreg-1.0", "trained_at": datetime.now(timezone.utc).date().isoformat(),
        "train_data": "NewsCLIPpings merged_balanced train (CLIP ViT-B/32 embeddings)",
        "threshold_data": "NewsCLIPpings merged_balanced val",
        "threshold_agree": hi, "threshold_disagree": lo, "validated": True,
        "metrics": {"accuracy": result["test"]["accuracy"], "auc": result["test"]["auc"]},
        "mean": mean.tolist(), "scale": scale.tolist(), "coef": clf.coef_[0].tolist(),
        "intercept": float(clf.intercept_[0])}))
    res = ROOT / "eval" / "results" / "consistency_newsclippings.json"
    res.parent.mkdir(exist_ok=True)
    res.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "external" / "newsclippings"))
