import importlib
import sys
import time
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture
def client(tmp_path, monkeypatch):
    """App with isolated storage, models off and no provider keys (unless a test sets them)."""
    monkeypatch.setenv("SAQRSIGHT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SAQRSIGHT_ENABLE_MODELS", "0")
    for k in ("GOOGLE_VISION_API_KEY", "BRAVE_SEARCH_API_KEY", "GOOGLE_CSE_API_KEY", "GOOGLE_CSE_CX"):
        monkeypatch.delenv(k, raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as c:
        c.app_module = app
        yield c


def wait(client, rid, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        p = client.get(f"/api/reports/{rid}").json()
        if p["status"] == "complete":
            return p
        time.sleep(0.1)
    raise AssertionError("report did not complete")


def png(size=(64, 48), color="green"):
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def mp4(path: Path, seconds=3, fps=10, size=(96, 64)):
    import cv2
    import numpy as np
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
    for i in range(seconds * fps):
        frame = np.full((size[1], size[0], 3), (i * 7) % 255, dtype=np.uint8)
        w.write(frame)
    w.release()
    return path.read_bytes()
