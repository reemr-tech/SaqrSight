"""Machine-learning comparison for the text indicators: TF-IDF + logistic regression.

One binary classifier per category (urgency, fear, manipulation, share_pressure) on character
n-grams of the normalised text (handles Arabic prefixes/suffixes and dialect spelling).

  train: eval/data/text_indicators_dev.jsonl + text_indicators_dev_dialect.jsonl (+ real_dev if present)
  test : text_indicators_real_test.jsonl (if present), test_v2 (blind) and test (v1)
No hyper-parameter tuning is done (there is no separate validation set at this size), so the
settings below are fixed defaults. With ~90 training posts this is a small-data baseline; rerun
it when the real labelled posts from eval/annotation are available.

Usage: python -I eval/eval_text_ml.py
Output: eval/results/text_ml.json
"""
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from saqrsight.analysis.lexicon import CATEGORIES  # noqa: E402
from saqrsight.textutil import normalize  # noqa: E402

DATA = ROOT / "eval" / "data"
CATS = list(CATEGORIES)


def load(name):
    path = DATA / f"text_indicators_{name}.jsonl"
    return [json.loads(x) for x in open(path, encoding="utf-8")] if path.exists() else []


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
    rnd = lambda x: None if x is None else round(x, 3)  # noqa: E731
    return {"precision": rnd(p), "recall": rnd(r), "f1": rnd(f), "tp": tp, "fp": fp, "fn": fn}


def score(rows, preds):
    out = {}
    for c in CATS:
        tp = sum(c in p and c in r["labels"] for p, r in zip(preds, rows))
        fp = sum(c in p and c not in r["labels"] for p, r in zip(preds, rows))
        fn = sum(c not in p and c in r["labels"] for p, r in zip(preds, rows))
        out[c] = prf(tp, fp, fn)
    out["micro"] = prf(*[sum(out[c][k] for c in CATS) for k in ("tp", "fp", "fn")])
    for ph in ("negation", "quote", "debunk", "warning", "neutral"):
        sub = [p for p, r in zip(preds, rows) if r["phenomenon"] == ph]
        if sub:
            out[f"false_alarm_rate_{ph}"] = {"rate": round(sum(bool(p) for p in sub) / len(sub), 3), "n": len(sub)}
    return out


def main():
    train = load("dev") + load("dev_dialect") + load("real_dev")
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=1, sublinear_tf=True)
    X = vec.fit_transform([normalize(r["text"]) for r in train])
    models = {}
    for c in CATS:
        y = np.array([c in r["labels"] for r in train], dtype=int)
        models[c] = LogisticRegression(C=1.0, class_weight="balanced", max_iter=2000).fit(X, y)
    results = {"model": "tfidf-char2-5+logreg (one per category)", "train_size": len(train)}
    splits = [x for x in ("real_test", "test_v2", "test") if load(x)]
    for split in splits:
        rows = load(split)
        Xt = vec.transform([normalize(r["text"]) for r in rows])
        probs = {c: models[c].predict_proba(Xt)[:, 1] for c in CATS}
        preds = [{c for c in CATS if probs[c][i] >= 0.5} for i in range(len(rows))]
        results[split] = {}
        for lang in ("en", "ar", "all"):
            idx = [i for i, r in enumerate(rows) if lang == "all" or r["lang"] == lang]
            sub_rows, sub_preds = [rows[i] for i in idx], [preds[i] for i in idx]
            results[split][lang] = {"n": len(idx), "metrics": score(sub_rows, sub_preds)}
            if lang != "all":
                results[split][lang]["errors"] = [
                    {"id": r["id"], "phenomenon": r["phenomenon"], "text": r["text"],
                     "missed": sorted(set(r["labels"]) - p), "extra": sorted(p - set(r["labels"]))}
                    for r, p in zip(sub_rows, sub_preds) if p != set(r["labels"])]
    out = ROOT / "eval" / "results" / "text_ml.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    for split in splits:
        for lang in ("en", "ar"):
            if not results[split][lang]["n"]:
                continue
            m = results[split][lang]["metrics"]
            fa = {k.replace("false_alarm_rate_", ""): v["rate"] for k, v in m.items() if k.startswith("false_alarm")}
            print(f"{split:7} {lang} micro P{m['micro']['precision']} R{m['micro']['recall']} F{m['micro']['f1']}  false alarms {fa}")


if __name__ == "__main__":
    main()
