"""Evaluate evidence retrieval.

1. Offline (always runs): the relevance/stance judgement applied to official-source results, on
   hand-labelled claim/result pairs in eval/data/retrieval_judgements.jsonl (same event/place/time,
   older coverage, different place, missing date, denials). Reports accuracy and a confusion table.
   Provider behaviour for unrelated matches, missing dates, no results and failures is covered by
   tests/test_modules.py with mocked responses.

2. Live (only with --live and provider keys): for each claim in a labelled file
   (eval/data/retrieval_live.jsonl: {"claim":..., "relevant_urls":[...]}) run the configured
   official-source search and record whether a known relevant URL appears in the top 5 results
   ("hit@5"). For reverse image search use {"image": path, "earlier_urls": [...]}.
   No live results are reported in the README until this has been run with real keys.

Usage: python -I eval/eval_retrieval.py [--live]
Output: eval/results/retrieval.json
"""
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from saqrsight.analysis import claims  # noqa: E402
from saqrsight.config import settings  # noqa: E402
from saqrsight.evidence import official_sources, reverse_image  # noqa: E402

TODAY = date(2026, 11, 4)   # fixed reference date the labelled pairs were written against


def offline():
    rows = [json.loads(x) for x in open(ROOT / "eval/data/retrieval_judgements.jsonl", encoding="utf-8")]
    conf, wrong = Counter(), []
    for r in rows:
        res = dict(r["result"])
        res["date"] = date.fromisoformat(res["date"]) if res["date"] else None
        pred = official_sources.judge(res, claims.extract(r["claim"]), TODAY)["relation"]
        conf[(r["gold"], pred)] += 1
        if pred != r["gold"]:
            wrong.append({"claim": r["claim"], "title": r["result"]["title"], "gold": r["gold"], "pred": pred})
    acc = sum(v for (g, p), v in conf.items() if g == p) / len(rows)
    labels = ["supporting", "contradicting", "insufficient"]
    per = {}
    for lab in labels:
        tp = conf[(lab, lab)]
        fp = sum(conf[(g, lab)] for g in labels if g != lab)
        fn = sum(conf[(lab, p)] for p in labels if p != lab)
        per[lab] = {"precision": round(tp / (tp + fp), 3) if tp + fp else None,
                    "recall": round(tp / (tp + fn), 3) if tp + fn else None, "n": tp + fn}
    return {"n": len(rows), "accuracy": round(acc, 3), "per_label": per,
            "confusion": {f"{g}->{p}": v for (g, p), v in sorted(conf.items())}, "errors": wrong}


def live():
    cfg = settings()
    out = {}
    path = ROOT / "eval/data/retrieval_live.jsonl"
    if not path.exists():
        return {"status": "no labelled live file"}
    rows = [json.loads(x) for x in open(path, encoding="utf-8")]
    hits, n = 0, 0
    for r in rows:
        if "claim" in r:
            res = official_sources.analyze(r["claim"], claims.extract(r["claim"]), True, cfg)
            urls = [s["url"] for f in res.findings for s in f.sources][:5]
            n += 1
            hits += any(u in r["relevant_urls"] for u in urls)
    out["official_hit_at_5"] = round(hits / n, 3) if n else None
    out["n"] = n
    _ = reverse_image   # reverse-image live evaluation follows the same pattern with "image" rows
    return out


def main():
    result = {"offline_judgement": offline()}
    if "--live" in sys.argv:
        result["live"] = live()
    out = ROOT / "eval/results/retrieval.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
