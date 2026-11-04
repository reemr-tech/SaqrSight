"""Lazy, thread-safe loading of the local ML models. Nothing is downloaded until first use."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from ..config import ROOT

_lock = threading.Lock()
_cache: dict[str, Any] = {}
CALIBRATION_DIR = ROOT / "models"


class ModelUnavailable(Exception):
    pass


def _get(key: str, factory):
    with _lock:
        if key not in _cache:
            try:
                _cache[key] = factory()
            except Exception as e:  # missing package, no network on first run, bad model id ...
                raise ModelUnavailable(f"{key}: {type(e).__name__}") from e
        return _cache[key]


def image_classifier(model_id: str):
    def make():
        from transformers import pipeline
        return pipeline("image-classification", model=model_id, device="cpu")
    return _get("cls:" + model_id, make)


def sentence_model(model_id: str):
    def make():
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(model_id, device="cpu")
    return _get("st:" + model_id, make)


def load_calibration(name: str) -> dict | None:
    """Calibration/validation records produced by the scripts in eval/. None => not validated."""
    path = CALIBRATION_DIR / name
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def calibration_path(name: str) -> Path:
    return CALIBRATION_DIR / name
