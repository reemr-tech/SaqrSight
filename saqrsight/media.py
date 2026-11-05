"""Upload validation and preprocessing for still images and short videos.

Files are validated by decoding them, never by their extension or declared content type.
Stored copies use internal names inside the report's private media folder.
"""
from __future__ import annotations

import shutil
import tempfile
import warnings
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .config import Settings


class SubmissionError(Exception):
    def __init__(self, status: int, message: str, code: str):
        super().__init__(message)
        self.status, self.message, self.code = status, message, code


@dataclass
class Visual:
    """One still image analysed by the visual modules: the uploaded image or a sampled video frame."""
    ref: str                     # "image" or "frame-1", "frame-2", ...
    path: Path
    width: int
    height: int
    timestamp: float | None = None   # seconds into the video, for frames

    def public(self) -> dict:
        d = {"ref": self.ref, "width": self.width, "height": self.height}
        if self.timestamp is not None:
            d["timestamp"] = round(self.timestamp, 2)
        return d


@dataclass
class MediaInfo:
    kind: str                    # "image" or "video"
    original_name: str
    width: int
    height: int
    visuals: list[Visual] = field(default_factory=list)
    duration: float | None = None
    fps: float | None = None

    def public(self) -> dict:
        d = {"kind": self.kind, "original_name": self.original_name, "width": self.width,
             "height": self.height, "visuals": [v.public() for v in self.visuals]}
        if self.kind == "video":
            d["duration"] = round(self.duration or 0, 2)
        return d


def safe_display_name(name: str) -> str:
    return Path((name or "upload").replace("\\", "/")).name[:200] or "upload"


def sniff_kind(raw: bytes) -> str | None:
    """Identify the container from magic bytes."""
    if raw[:3] == b"\xff\xd8\xff" or raw[:8] == b"\x89PNG\r\n\x1a\n" or (raw[:4] == b"RIFF" and raw[8:12] == b"WEBP"):
        return "image"
    if raw[4:8] == b"ftyp" or raw[:4] == b"\x1a\x45\xdf\xa3":
        return "video"
    return None


def _open_image(raw: bytes, cfg: Settings) -> Image.Image:
    Image.MAX_IMAGE_PIXELS = cfg.max_image_pixels
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            im = Image.open(BytesIO(raw))
            if im.format not in {"JPEG", "PNG", "WEBP"}:
                raise SubmissionError(415, "Use a JPEG, PNG, or WebP image.", "unsupported_image")
            if getattr(im, "n_frames", 1) != 1:
                raise SubmissionError(415, "Use a single still image, not an animated file.", "animated_image")
            im.load()
            return im
    except SubmissionError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise SubmissionError(
            415, f"The image could not be decoded, or it exceeds the {cfg.max_image_pixels / 1e6:.0f}-megapixel limit.",
            "invalid_image")


def process_image(raw: bytes, name: str, folder: Path, cfg: Settings) -> MediaInfo:
    if len(raw) > cfg.max_image_bytes:
        raise SubmissionError(413, f"Images must be {cfg.max_image_bytes // 2**20} MB or smaller.", "image_too_large")
    im = _open_image(raw, cfg)
    if min(im.size) < cfg.min_image_side:
        raise SubmissionError(422, f"Images must be at least {cfg.min_image_side} pixels on each side.", "image_too_small")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "image.jpg"
    # Re-encode: strips EXIF/GPS metadata and never stores arbitrary upload bytes.
    im.convert("RGB").save(path, format="JPEG", quality=92)
    v = Visual("image", path, im.width, im.height)
    return MediaInfo("image", safe_display_name(name), im.width, im.height, [v])


def process_video(raw: bytes, name: str, folder: Path, cfg: Settings) -> MediaInfo:
    if len(raw) > cfg.max_video_bytes:
        raise SubmissionError(413, f"Videos must be {cfg.max_video_bytes // 2**20} MB or smaller.", "video_too_large")
    try:
        import cv2  # opencv-python-headless
    except ImportError:
        raise SubmissionError(415, "Video support is not installed on this server.", "video_unsupported")
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".bin", dir=folder, delete=False) as tmp:
        tmp.write(raw)
        tmp_path = Path(tmp.name)
    try:
        cap = cv2.VideoCapture(str(tmp_path))
        if not cap.isOpened():
            raise SubmissionError(415, "The video could not be decoded. Use MP4, MOV or WebM.", "invalid_video")
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        if fps <= 0 or count <= 0 or width <= 0:
            raise SubmissionError(415, "The video could not be decoded. Use MP4, MOV or WebM.", "invalid_video")
        duration = count / fps
        if duration > cfg.max_video_seconds:
            raise SubmissionError(413, f"Videos must be {cfg.max_video_seconds:.0f} seconds or shorter.", "video_too_long")
        if width * height > cfg.max_image_pixels:
            raise SubmissionError(415, "Video resolution is too large.", "video_resolution")
        n = max(1, min(cfg.video_frames, count))
        visuals: list[Visual] = []
        for i in range(n):
            # Evenly spaced, centred in each segment so the first/last black frames are avoided.
            t = (i + 0.5) * duration / n
            cap.set(cv2.CAP_PROP_POS_FRAMES, min(count - 1, int(t * fps)))
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            rgb = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            path = folder / f"frame-{len(visuals) + 1}.jpg"
            rgb.save(path, format="JPEG", quality=92)
            visuals.append(Visual(f"frame-{len(visuals) + 1}", path, rgb.width, rgb.height, t))
        cap.release()
        if not visuals:
            raise SubmissionError(415, "No frames could be decoded from the video.", "invalid_video")
        return MediaInfo("video", safe_display_name(name), width, height, visuals, duration, fps)
    except SubmissionError:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    finally:
        tmp_path.unlink(missing_ok=True)   # only the sampled frames are retained


def process_upload(raw: bytes, name: str, folder: Path, cfg: Settings) -> MediaInfo:
    if not raw:
        raise SubmissionError(422, "The uploaded file is empty.", "empty_file")
    kind = sniff_kind(raw[:16])
    if kind == "image":
        return process_image(raw, name, folder, cfg)
    if kind == "video":
        return process_video(raw, name, folder, cfg)
    if len(raw) > max(cfg.max_image_bytes, cfg.max_video_bytes):
        raise SubmissionError(413, "The file is larger than the upload limits.", "file_too_large")
    raise SubmissionError(415, "Unsupported file. Use a JPEG, PNG or WebP image, or an MP4, MOV or WebM video.",
                          "unsupported_file")


def model_input(path: Path, size: int = 224) -> Image.Image:
    """Load a stored visual as RGB for a model; the model's own processor does the final resize."""
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((size * 4, size * 4))
        return im
