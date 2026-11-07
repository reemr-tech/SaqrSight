"""Inter-annotator agreement for the text-indicator labels.

Compares two annotators' CSV files (same ids, see GUIDELINES.md) and reports, per category:
percent agreement and Cohen's kappa. Writes disagreements.csv next to the first file so the
annotators can discuss and agree final labels.

Usage: python -I eval/annotation/agreement.py annotator_A.csv annotator_B.csv
"""
import csv
import sys
from pathlib import Path

CATS = ["urgency", "fear", "manipulation", "share_pressure"]


def read(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {r["id"].strip(): r for r in csv.DictReader(f) if r.get("id", "").strip()}


def label(v):
    return 1 if str(v).strip() in ("1", "1.0", "yes", "y", "true") else 0


def kappa(a, b):
    n = len(a)
    if n == 0:
        return None, None
    po = sum(x == y for x, y in zip(a, b)) / n
    pa1, pb1 = sum(a) / n, sum(b) / n
    pe = pa1 * pb1 + (1 - pa1) * (1 - pb1)
    k = None if pe == 1 else (po - pe) / (1 - pe)
    return po, k


def kappa_multi(a, b):
    """Cohen's kappa for more than two classes (unweighted)."""
    n = len(a)
    if n == 0:
        return None, None
    po = sum(x == y for x, y in zip(a, b)) / n
    labels = set(a) | set(b)
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in labels)
    return po, (None if pe == 1 else (po - pe) / (1 - pe))


def main(a_path, b_path):
    A, B = read(a_path), read(b_path)
    ids = sorted(set(A) & set(B))
    only = sorted(set(A) ^ set(B))
    print(f"posts labelled by both: {len(ids)}" + (f"  (ignored, only in one file: {len(only)})" if only else ""))
    rows = []
    print(f"{'category':15} {'agreement':>10} {'kappa':>7}  (A=1 / B=1)")
    for c in CATS:
        a = [label(A[i].get(c)) for i in ids]
        b = [label(B[i].get(c)) for i in ids]
        po, k = kappa(a, b)
        print(f"{c:15} {po:>10.2%} {('n/a' if k is None else f'{k:.2f}'):>7}  ({sum(a)} / {sum(b)})")
    pa = [str(A[i].get("panic_level", "")).strip().lower() for i in ids]
    pb = [str(B[i].get("panic_level", "")).strip().lower() for i in ids]
    if any(pa) and any(pb):
        po, k = kappa_multi(pa, pb)
        print(f"{'panic_level':15} {po:>10.2%} {('n/a' if k is None else f'{k:.2f}'):>7}  (3 levels: none/mild/strong)")
    for i in ids:
        diff = [c for c in CATS if label(A[i].get(c)) != label(B[i].get(c))]
        if str(A[i].get("panic_level", "")).strip().lower() != str(B[i].get("panic_level", "")).strip().lower():
            diff.append("panic_level")
        if diff:
            rows.append({"id": i, "text": A[i].get("text", ""), "categories_in_disagreement": " ".join(diff),
                         **{f"A_{c}": label(A[i].get(c)) for c in CATS}, **{f"B_{c}": label(B[i].get(c)) for c in CATS}})
    out = Path(a_path).with_name("disagreements.csv")
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        fields = ["id", "text", "categories_in_disagreement"] + [f"A_{c}" for c in CATS] + [f"B_{c}" for c in CATS]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} posts with disagreements written to {out}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
