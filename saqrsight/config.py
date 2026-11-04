"""Runtime configuration. Every limit can be overridden with an environment variable.

Credentials are read only from the environment (see .env.example) and are never logged.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    """Read lazily so tests can change the environment and reload."""

    def __init__(self) -> None:
        self.data_dir = Path(os.environ.get("SAQRSIGHT_DATA_DIR", ROOT / "data")).resolve()
        self.media_dir = self.data_dir / "media"
        self.db_path = self.data_dir / "saqrsight.sqlite3"

        # Submission limits (shown to the user through /api/config).
        self.max_text_chars = _int("SAQRSIGHT_MAX_TEXT_CHARS", 10_000)
        self.max_image_bytes = _int("SAQRSIGHT_MAX_IMAGE_MB", 10) * 1024 * 1024
        self.max_image_pixels = _int("SAQRSIGHT_MAX_IMAGE_PIXELS", 20_000_000)
        self.min_image_side = _int("SAQRSIGHT_MIN_IMAGE_SIDE", 32)
        self.max_video_bytes = _int("SAQRSIGHT_MAX_VIDEO_MB", 50) * 1024 * 1024
        self.max_video_seconds = _float("SAQRSIGHT_MAX_VIDEO_SECONDS", 60.0)
        self.video_frames = _int("SAQRSIGHT_VIDEO_FRAMES", 5)

        # Analysis modules. Model-based modules can be switched off (e.g. on low-memory machines).
        self.enable_models = _bool("SAQRSIGHT_ENABLE_MODELS", True)
        self.visual_model = os.environ.get("SAQRSIGHT_VISUAL_MODEL", "Organika/sdxl-detector")
        self.clip_image_model = os.environ.get("SAQRSIGHT_CLIP_IMAGE_MODEL", "clip-ViT-B-32")
        self.clip_text_model = os.environ.get(
            "SAQRSIGHT_CLIP_TEXT_MODEL", "sentence-transformers/clip-ViT-B-32-multilingual-v1")
        self.module_timeout = _float("SAQRSIGHT_MODULE_TIMEOUT", 120.0)

        # Optional evidence providers. Absent keys => "not configured".
        self.google_vision_key = os.environ.get("GOOGLE_VISION_API_KEY", "")
        self.search_provider = os.environ.get("SAQRSIGHT_SEARCH_PROVIDER", "brave").lower()
        self.brave_key = os.environ.get("BRAVE_SEARCH_API_KEY", "")
        self.google_cse_key = os.environ.get("GOOGLE_CSE_API_KEY", "")
        self.google_cse_cx = os.environ.get("GOOGLE_CSE_CX", "")
        self.http_timeout = _float("SAQRSIGHT_HTTP_TIMEOUT", 15.0)
        self.max_search_queries = _int("SAQRSIGHT_MAX_SEARCH_QUERIES", 4)
        self.max_reverse_frames = _int("SAQRSIGHT_MAX_REVERSE_FRAMES", 2)
        domains = os.environ.get("SAQRSIGHT_OFFICIAL_DOMAINS", "")
        self.official_domains = [d.strip().lower() for d in domains.split(",") if d.strip()] or DEFAULT_OFFICIAL_DOMAINS

        # Retention: reports older than this many days are purged at startup (0 = keep until deleted).
        self.retention_days = _int("SAQRSIGHT_RETENTION_DAYS", 30)

    @property
    def reverse_search_configured(self) -> bool:
        return bool(self.google_vision_key)

    @property
    def official_search_configured(self) -> bool:
        if self.search_provider == "google_cse":
            return bool(self.google_cse_key and self.google_cse_cx)
        return bool(self.brave_key)

    def public_limits(self) -> dict:
        return {
            "max_text_chars": self.max_text_chars,
            "max_image_mb": self.max_image_bytes // (1024 * 1024),
            "max_image_megapixels": round(self.max_image_pixels / 1_000_000, 1),
            "min_image_side": self.min_image_side,
            "image_formats": ["JPEG", "PNG", "WebP"],
            "max_video_mb": self.max_video_bytes // (1024 * 1024),
            "max_video_seconds": self.max_video_seconds,
            "video_formats": ["MP4", "MOV", "WebM"],
            "video_frames_sampled": self.video_frames,
            "retention_days": self.retention_days,
        }


# Selected official UAE sources (government entities and the official news agency).
DEFAULT_OFFICIAL_DOMAINS = [
    "wam.ae",            # Emirates News Agency
    "u.ae",              # UAE government portal
    "mediaoffice.ae",    # Dubai Media Office
    "mediaoffice.abudhabi",  # Abu Dhabi Media Office
    "ncema.gov.ae",      # National Emergency Crisis and Disaster Management Authority
    "moi.gov.ae",        # Ministry of Interior
    "dubaipolice.gov.ae",
    "adpolice.gov.ae",
    "ncm.gov.ae",        # National Centre of Meteorology
    "mohap.gov.ae",      # Ministry of Health and Prevention
]


def settings() -> Settings:
    return Settings()
