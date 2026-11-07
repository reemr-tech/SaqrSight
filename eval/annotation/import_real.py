"""Load adjudicated real posts into the evaluation data.

Reads the agreed labels (CSV in the template format), removes duplicates (same normalised text),
and splits the posts into:
  eval/data/text_indicators_real_dev.jsonl   development half: may be used to improve rules / train the model
  eval/data/text_indicators_real_test.jsonl  test half: never used for changes – report results on this
The split is fixed by a hash of the normalised text, so re-running gives the same split and near-copies
of a post cannot land on both sides. Each language is split separately.

Usage: python -I eval/annotation/import_real.py adjudicated.csv
"""
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from saqrsight.textutil import normalize  # noqa: E402

CATS = ["urgency", "fear", "manipulation", "share_pressure"]
PHENOMENA = {"indicator", "dialect", "negation", "quote", "debunk", "warning", "neutral"}


def key(text):
    t = re.sub(r"[^\w\s]", "", normalize(text))      # punctuation/emoji do not make a post "new"
    return re.sub(r"\s+", " ", t).strip()


def main(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r.get("text", "").strip()]
    seen, posts, problems = set(), [], []
    for r in rows:
        k = key(r["text"])
        if k in seen:
            problems.append(f"duplicate skipped: {r.get('id')}")
            continue
        seen.add(k)
        lang = r.get("lang", "").strip().lower()
        ph = r.get("phenomenon", "").strip().lower() or "indicator"
        if lang not in ("ar", "en"):
            problems.append(f"{r.get('id')}: lang must be ar or en")
            continue
        if ph not in PHENOMENA:
            problems.append(f"{r.get('id')}: unknown phenomenon '{ph}'")
            continue
        labels = [c for c in CATS if str(r.get(c, "0")).strip() in ("1", "1.0", "yes", "y", "true")]
        panic = str(r.get("panic_level", "")).strip().lower()
        if panic and panic not in ("none", "mild", "strong"):
            problems.append(f"{r.get('id')}: panic_level must be none, mild or strong")
            continue
        posts.append({"id": r.get("id") or f"real-{len(posts) + 1}", "lang": lang, "text": r["text"].strip(),
                      "labels": labels, "phenomenon": ph, "source_type": r.get("source_type", "").strip(),
                      **({"panic_level": panic} if panic else {}),
                      "_k": k})
    dev, test = [], []
    for p in posts:
        h = int(hashlib.sha256(p.pop("_k").encode()).hexdigest(), 16)
        (test if h % 2 else dev).append(p)
    data = ROOT / "eval" / "data"
    for name, part in (("real_dev", dev), ("real_test", test)):
        with open(data / f"text_indicators_{name}.jsonl", "w", encoding="utf-8") as f:
            for p in part:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
    for msg in problems:
        print("warning:", msg)
    for name, part in (("real_dev", dev), ("real_test", test)):
        en = sum(p["lang"] == "en" for p in part)
        print(f"{name}: {len(part)} posts ({en} English, {len(part) - en} Arabic)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
