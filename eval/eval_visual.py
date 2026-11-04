"""Evaluate candidate AI-generated-image detectors and select one (or none) for the report.

Data: ELSA_D3 validation shard 0 (elsaEU/ELSA_D3 on Hugging Face). Each row has a real web image
(LAION URL) and four images generated from a caption of that same image (DeepFloyd IF, SD 1.4,
SD 2.1, SDXL). We keep rows whose real URL still resolves, and pair each real image with ONE
generated image, rotating generators so they are balanced.

Leakage and shortcut controls
  * dev/test split by row: a real image and its generated counterpart never cross splits.
  * both classes are re-encoded to JPEG q=90 before scoring ("standard"), so file format and
    compression history cannot separate the classes.
  * candidate choice and threshold use dev only; test is scored once per condition.
  * we cannot verify that candidates were not trained on ELSA/LAION images; see README.

Conditions on test: standard, jpeg_q50 (heavy recompression), resized_50 (half resolution),
screenshot (image shown at 600px in a UI frame, captured as PNG).

Acceptance rule for using the signal in the report: on the standard test condition,
precision >= 0.80 and false-positive rate on authentic images <= 0.15.

Usage: python -I eval/eval_visual.py external/elsa/val0.parquet
Output: eval/results/visual.json, models/visual_calibration.json
"""
import concurrent.futures as cf
import io
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np
import pyarrow.parquet as pq
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from saqrsight.analysis.visual import score_images  # noqa: E402

CANDIDATES = ["Organika/sdxl-detector", "haywoodsloan/ai-image-detector-deploy", "Ateeqq/ai-vs-human-image-detector"]
Image.MAX_IMAGE_PIXELS = 40_000_000
CACHE = ROOT / "external" / "elsa" / "real"


def fetch_real(row):
    path = CACHE / f"{row['id']}.jpg"
    if path.exists():
        return row["id"], path
    try:
        r = httpx.get(row["url"].replace("&amp;", "&"), timeout=8, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0 (research evaluation)"})
        if r.status_code != 200 or len(r.content) > 15_000_000:
            return row["id"], None
        im = Image.open(io.BytesIO(r.content))
        im.load()
        if min(im.size) < 128:
            return row["id"], None
        im.convert("RGB").save(path, "JPEG", quality=95)
        return row["id"], path
    except Exception:
        return row["id"], None


def jpeg(im, q):
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=q)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def screenshot(im):
    im = im.copy()
    im.thumbnail((600, 600))
    canvas = Image.new("RGB", (im.width + 80, im.height + 160), (245, 245, 245))
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 0, canvas.width, 50], fill=(30, 30, 30))
    d.text((12, 18), "@user · 2h", fill=(230, 230, 230))
    d.text((40, im.height + 90), "1.2K likes  340 reposts", fill=(90, 90, 90))
    canvas.paste(im, (40, 70))
    buf = io.BytesIO()
    canvas.save(buf, "PNG")
    buf.seek(0)
    return Image.open(buf).convert("RGB")


CONDITIONS = {
    "standard": lambda im: jpeg(im, 90),
    "jpeg_q50": lambda im: jpeg(jpeg(im, 90), 50),
    "resized_50": lambda im: jpeg(im.resize((max(1, im.width // 2), max(1, im.height // 2))), 90),
    "screenshot": lambda im: screenshot(jpeg(im, 90)),
}


def metrics(y, s, t):
    pred = s >= t
    tp, fp = int((pred & (y == 1)).sum()), int((pred & (y == 0)).sum())
    fn, tn = int((~pred & (y == 1)).sum()), int((~pred & (y == 0)).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(prec, 3), "recall": round(rec, 3),
            "f1": round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0.0,
            "fpr": round(fp / (fp + tn), 3) if fp + tn else 0.0, "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def choose_threshold(y, s, max_fpr=0.10):
    best = 0.5
    for t in np.round(np.arange(0.05, 1.0, 0.01), 2):
        if metrics(y, s, t)["fpr"] <= max_fpr:
            best = float(t)
            break
    return best


def main(parquet: Path):
    CACHE.mkdir(parents=True, exist_ok=True)
    table = pq.read_table(parquet)
    rows = table.select(["id", "url"]).to_pylist()
    with cf.ThreadPoolExecutor(16) as ex:
        real = dict(ex.map(fetch_real, rows))
    kept = [i for i, r in enumerate(rows) if real[r["id"]] is not None]
    print(f"real images fetched: {len(kept)} of {len(rows)}")
    data = []
    for n, i in enumerate(kept):
        g = n % 4
        gen = table.column(f"image_gen{g}")[i].as_py()
        data.append({"id": rows[i]["id"], "real": real[rows[i]["id"]], "gen_bytes": gen["bytes"],
                     "generator": table.column(f"model_gen{g}")[i].as_py()})
    random.Random(13).shuffle(data)
    half = len(data) // 2
    splits = {"dev": data[:half], "test": data[half:]}

    def images(split, cond):
        ims, y, gens = [], [], []
        for d in splits[split]:
            ims.append(CONDITIONS[cond](Image.open(d["real"]).convert("RGB"))); y.append(0); gens.append("real")
            ims.append(CONDITIONS[cond](Image.open(io.BytesIO(d["gen_bytes"])).convert("RGB"))); y.append(1)
            gens.append(d["generator"])
        return ims, np.array(y), np.array(gens)

    results = {"dataset": "ELSA_D3 validation shard 0", "pairs": {k: len(v) for k, v in splits.items()},
               "generators": sorted({d["generator"] for d in data}), "candidates": {}}
    dev_ims, dev_y, _ = images("dev", "standard")
    for model in CANDIDATES:
        s = np.array(score_images(model, dev_ims))
        t = choose_threshold(dev_y, s)
        res = {"threshold": t, "dev": metrics(dev_y, s, t), "test": {}}
        for cond in CONDITIONS:
            ims, y, gens = images("test", cond)
            st = np.array(score_images(model, ims))
            res["test"][cond] = metrics(y, st, t)
            if cond == "standard":
                res["test_recall_by_generator"] = {
                    g: round(float((st[gens == g] >= t).mean()), 3) for g in sorted(set(gens)) if g != "real"}
        results["candidates"][model] = res
        print(model, json.dumps(res))
    ok = {m: r for m, r in results["candidates"].items()
          if r["test"]["standard"]["precision"] >= 0.80 and r["test"]["standard"]["fpr"] <= 0.15}
    # among acceptable models, pick the best dev F1 (test is not used to rank)
    selected = max(ok, key=lambda m: results["candidates"][m]["dev"]["f1"]) if ok else None
    results["selected"] = selected
    results["acceptance_rule"] = "test standard: precision >= 0.80 and FPR <= 0.15; rank by dev F1"
    out = ROOT / "eval" / "results" / "visual.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, indent=2))
    cal = {"evaluated_at": datetime.now(timezone.utc).date().isoformat(), "dataset": results["dataset"],
           "selected": bool(selected), "model": selected,
           "threshold": results["candidates"][selected]["threshold"] if selected else None,
           "test_size": 2 * len(splits["test"]),
           "metrics": results["candidates"][selected]["test"]["standard"] if selected else None,
           "robustness": results["candidates"][selected]["test"] if selected else None}
    (ROOT / "models").mkdir(exist_ok=True)
    (ROOT / "models" / "visual_calibration.json").write_text(json.dumps(cal, indent=2))
    print("selected:", selected)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
