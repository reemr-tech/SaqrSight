"""Independent evaluation of the consistency check on VERITE (Papadopoulos et al., 2024).

VERITE is never used for training or threshold selection: the classifier and thresholds come
from NewsCLIPpings (train_consistency.py) and are loaded unchanged.

Images are fetched from the URLs published in VERITE_articles.csv (research use only); many
are no longer reachable, so results cover the subset whose images could be downloaded, and the
count is reported. Labels: true, miscaptioned, out-of-context.

Two text encoders are compared on the same images and classifier:
  openai   - the CLIP ViT-B/32 text encoder the classifier was trained with (English only)
  multi    - the multilingual encoder the app uses (needed for Arabic)

Key metric beyond accuracy: how often miscaptioned / out-of-context pairs are labelled "agree"
(the system would wrongly treat the caption as supported by the image).

Usage: python -I eval/eval_consistency_verite.py external/verite
Output: eval/results/consistency_verite.json
"""
import concurrent.futures as cf
import csv
import io
import json
import sys
from pathlib import Path

import httpx
import numpy as np
from PIL import Image
from sklearn.metrics import precision_recall_fscore_support, roc_auc_score

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from saqrsight.analysis.consistency import features, predict_proba  # noqa: E402
from saqrsight.analysis.models import load_calibration, sentence_model  # noqa: E402

Image.MAX_IMAGE_PIXELS = 40_000_000


def fetch(item):
    url, path = item
    if path.exists():
        return path, True
    try:
        r = httpx.get(url, timeout=10, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (research evaluation)"})
        if r.status_code != 200:
            return path, False
        im = Image.open(io.BytesIO(r.content))
        im.load()
        if min(im.size) < 64:
            return path, False
        im.convert("RGB").save(path, "JPEG", quality=95)
        return path, True
    except Exception:
        return path, False


def main(root: Path):
    img_dir = root / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    arts = list(csv.DictReader(open(root / "VERITE_articles.csv", encoding="utf-8")))
    jobs = []
    for i, a in enumerate(arts):
        jobs.append((a["true_url"], img_dir / f"true_{i}.jpg"))
        if a.get("false_url") and a["false_url"].startswith("http"):
            jobs.append((a["false_url"], img_dir / f"false_{i}.jpg"))
    with cf.ThreadPoolExecutor(16) as ex:
        ok = dict(ex.map(fetch, jobs))
    rows = [r for r in csv.DictReader(open(root / "VERITE.csv", encoding="utf-8"))
            if ok.get(img_dir / Path(r["image_path"]).name)]
    print(f"usable pairs: {len(rows)} of 1000 (images downloaded: {sum(ok.values())} of {len(jobs)})")

    clf = load_calibration("consistency_classifier.json")
    hi, lo = clf["threshold_agree"], clf["threshold_disagree"]
    img_model = sentence_model("clip-ViT-B-32")
    imgs = img_model.encode([Image.open(img_dir / Path(r["image_path"]).name).convert("RGB") for r in rows],
                            batch_size=32, convert_to_numpy=True)
    caps = [r["caption"] for r in rows]
    labels = np.array([r["label"] for r in rows])
    y = (labels == "true").astype(int)
    encoders = {"openai": img_model, "multi": sentence_model("sentence-transformers/clip-ViT-B-32-multilingual-v1")}
    result = {"usable_pairs": len(rows), "class_counts": {c: int((labels == c).sum()) for c in set(labels)},
              "thresholds": {"agree": hi, "disagree": lo}, "encoders": {}}
    for name, enc in encoders.items():
        txt = enc.encode(caps, batch_size=32, convert_to_numpy=True)
        p = predict_proba(clf, features(imgs, txt))
        pred = (p >= 0.5).astype(int)
        pr, rc, f1, _ = precision_recall_fscore_support(y, pred, labels=[1, 0], zero_division=0)
        decision = np.where(p >= hi, "agree", np.where(p <= lo, "disagree", "inconclusive"))
        per_class = {}
        for c in ("true", "miscaptioned", "out-of-context"):
            m = labels == c
            per_class[c] = {k: round(float((decision[m] == k).mean()), 3) for k in ("agree", "disagree", "inconclusive")}
        agree, disagree = decision == "agree", decision == "disagree"
        # For "true vs miscaptioned" (the subset the match/mismatch labels most closely address)
        tm = np.isin(labels, ["true", "miscaptioned"])
        result["encoders"][name] = {
            "binary_true_vs_false": {
                "auc": round(roc_auc_score(y, p), 3), "accuracy": round(float((pred == y).mean()), 3),
                "true": {"precision": round(pr[0], 3), "recall": round(rc[0], 3), "f1": round(f1[0], 3)},
                "false": {"precision": round(pr[1], 3), "recall": round(rc[1], 3), "f1": round(f1[1], 3)}},
            "true_vs_miscaptioned_auc": round(roc_auc_score(y[tm], p[tm]), 3),
            "true_vs_out_of_context_auc": round(roc_auc_score(y[labels != "miscaptioned"], p[labels != "miscaptioned"]), 3),
            "three_way": {"agree_precision": round(float(y[agree].mean()), 3) if agree.any() else None,
                          "disagree_precision": round(float(1 - y[disagree].mean()), 3) if disagree.any() else None,
                          "coverage": round(float((agree | disagree).mean()), 3)},
            "decision_by_class": per_class,
            "wrongly_supported_rate": {c: per_class[c]["agree"] for c in ("miscaptioned", "out-of-context")},
        }
        # Verdict level: apply the assessment rules (rules-1.1) to each pair's consistency decision.
        # NOTE: the A3 place/time condition was added after seeing the module-level VERITE results,
        # so this block is not a fully independent test of the rules.
        from saqrsight import assessment
        from saqrsight.analysis import claims as _claims
        verdicts = []
        for cap, dec in zip(caps, decision):
            mods = {"consistency_check": {"status": "completed", "confidence": "validated", "findings": [],
                                          "data": {"decision": dec}}}
            verdicts.append(assessment.assess(mods, _claims.extract(cap), True, True)["verdict"])
        verdicts = np.array(verdicts)
        result["encoders"][name]["verdict_by_class"] = {
            c: {v: round(float((verdicts[labels == c] == v).mean()), 3)
                for v in ("apparently_consistent", "potentially_misleading", "insufficient_evidence")}
            for c in ("true", "miscaptioned", "out-of-context")}
    out = ROOT / "eval" / "results" / "consistency_verite.json"
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
