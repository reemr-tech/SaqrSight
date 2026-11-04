"""Produce example HTML/JSON reports by running samples/sample_inputs.json through the real app.

Uses an isolated temporary data folder, so it never touches your saved reports.
Usage: python -I scripts/make_examples.py
Output: samples/example_reports/<id>.html and .json
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["SAQRSIGHT_DATA_DIR"] = tempfile.mkdtemp(prefix="saqr-examples-")
for k in ("GOOGLE_VISION_API_KEY", "BRAVE_SEARCH_API_KEY", "GOOGLE_CSE_API_KEY"):
    os.environ.pop(k, None)   # examples show the no-key configuration

from fastapi.testclient import TestClient  # noqa: E402

import app  # noqa: E402

out = ROOT / "samples" / "example_reports"
out.mkdir(parents=True, exist_ok=True)
samples = json.loads((ROOT / "samples" / "sample_inputs.json").read_text(encoding="utf-8"))
with TestClient(app.app) as c:
    for s in samples:
        files = None
        if s["media"]:
            mime = "video/mp4" if s["media"].endswith(".mp4") else "image/jpeg"
            files = {"media": (s["media"], (ROOT / "samples" / s["media"]).read_bytes(), mime)}
        r = c.post("/api/reports", data={"caption": s["caption"]}, files=files)
        r.raise_for_status()
        rid = r.json()["id"]
        for _ in range(600):
            p = c.get(f"/api/reports/{rid}").json()
            if p["status"] == "complete":
                break
            time.sleep(0.5)
        (out / f"{s['id']}.json").write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / f"{s['id']}.html").write_text(c.get(f"/api/reports/{rid}/download?format=html").text, encoding="utf-8")
        mods = {k: v["status"] + (f" ({v['data'].get('decision')})" if v["data"].get("decision") else "")
                for k, v in p["modules"].items()}
        print(f"{s['id']:16} {p['assessment']['verdict']:24} {p['assessment']['rule']} priority={p['priority']['level']:6} {mods}")
