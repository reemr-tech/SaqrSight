"""Evaluate the text-indicator baseline: per-category precision/recall/F1, by language and split.

A post counts as positive for a category if the module reports an *active* indicator of that
category (stylistic signals count as urgency). Errors are listed with their phenomenon tag so
negation, quotation, debunk and warning cases can be inspected.

Usage: python -I eval/eval_text.py
Output: eval/results/text.json (and a printed summary)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from saqrsight.analysis import text_indicators  # noqa: E402
from saqrsight.analysis.lexicon import CATEGORIES  # noqa: E402


SPLITS = [x for x in ("dev", "dev_dialect", "test", "test_v2")
          if (ROOT / "eval" / "data" / f"text_indicators_{x}.jsonl").exists()]


def predict(text):
    r = text_indicators.analyze(text, "")
    return set(r.data["categories"])


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
    rnd = lambda x: None if x is None else round(x, 3)  # noqa: E731
    return {"precision": rnd(p), "recall": rnd(r), "f1": rnd(f), "tp": tp, "fp": fp, "fn": fn}


def evaluate(rows):
    out, errors = {}, []
    preds = [predict(r["text"]) for r in rows]
    for cat in CATEGORIES:
        tp = sum(cat in p and cat in r["labels"] for p, r in zip(preds, rows))
        fp = sum(cat in p and cat not in r["labels"] for p, r in zip(preds, rows))
        fn = sum(cat not in p and cat in r["labels"] for p, r in zip(preds, rows))
        out[cat] = prf(tp, fp, fn)
    tot = [sum(out[c][k] for c in CATEGORIES) for k in ("tp", "fp", "fn")]
    out["micro"] = prf(*tot)
    # Post-level false alarms on cases that must NOT be flagged.
    for ph in ("negation", "quote", "debunk", "warning", "neutral"):
        sub = [(p, r) for p, r in zip(preds, rows) if r["phenomenon"] == ph]
        if sub:
            out[f"false_alarm_rate_{ph}"] = {"rate": round(sum(bool(p) for p, _ in sub) / len(sub), 3), "n": len(sub)}
    for p, r in zip(preds, rows):
        if p != set(r["labels"]):
            errors.append({"id": r["id"], "phenomenon": r["phenomenon"], "text": r["text"],
                           "missed": sorted(set(r["labels"]) - p), "extra": sorted(p - set(r["labels"]))})
    return out, errors


def main():
    results = {"model": text_indicators.VERSION}
    for split in SPLITS:
        rows = [json.loads(line) for line in open(ROOT / "eval" / "data" / f"text_indicators_{split}.jsonl", encoding="utf-8")]
        results[split] = {}
        for lang in ("en", "ar", "all"):
            sub = [r for r in rows if lang == "all" or r["lang"] == lang]
            m, errs = evaluate(sub)
            results[split][lang] = {"n": len(sub), "metrics": m}
            if lang != "all":
                results[split][lang]["errors"] = errs
    out = ROOT / "eval" / "results" / "text.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    for split in SPLITS:
        for lang in ("en", "ar"):
            r = results[split][lang]
            line = "  ".join(f"{c[:6]} P{r['metrics'][c]['precision']} R{r['metrics'][c]['recall']} F{r['metrics'][c]['f1']}"
                             for c in list(CATEGORIES) + ["micro"])
            print(f"{split:4} {lang} n={r['n']}: {line}")
            for e in r["errors"]:
                print(f"      {e['id']} [{e['phenomenon']}] missed={e['missed']} extra={e['extra']} :: {e['text'][:70]}")


if __name__ == "__main__":
    main()
