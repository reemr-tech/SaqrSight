"""SaqrSight SGP2: FastAPI entry point.

Operations
  GET    /api/config                         upload limits and which optional checks are available
  POST   /api/reports                        submit caption and/or one image or short video (202, processing)
  GET    /api/reports                        list saved reports (most recent 100)
  GET    /api/reports/{id}                   view a report (poll until status == "complete")
  GET    /api/reports/{id}/media/{ref}       stored image or sampled frame ("image", "frame-1", ...)
  GET    /api/reports/{id}/image             first stored visual (kept for SGP1 compatibility)
  GET    /api/reports/{id}/download?format=  html | json
  DELETE /api/reports/{id}                   delete report records and stored media
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from saqrsight import pipeline, report
from saqrsight.analysis import claims
from saqrsight.config import ROOT, settings
from saqrsight.media import SubmissionError, process_upload
from saqrsight.storage import Store
from saqrsight.textutil import detect_language

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
# HTTP client loggers print request URLs, which can carry API keys (?key=...). Keep them quiet.
for _name in ("httpx", "httpx2", "httpcore", "urllib3", "huggingface_hub"):
    logging.getLogger(_name).setLevel(logging.WARNING)
cfg = settings()
store = Store(cfg)
store.purge_expired()
DATA, MEDIA = cfg.data_dir, cfg.media_dir   # kept for tests and tooling
app = FastAPI(title="SaqrSight", version=pipeline.VERSION)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
NO_STORE = {"Cache-Control": "no-store"}


@app.exception_handler(SubmissionError)
def _submission_error(_: Request, e: SubmissionError):
    return JSONResponse({"detail": e.message, "code": e.code}, status_code=e.status)


def _record(report_id: str) -> dict:
    p = store.get(report_id)
    if p is None:
        raise HTTPException(404, "Report not found.")
    return p


@app.get("/", response_class=HTMLResponse)
def home():
    return (ROOT / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
def health():
    return {"status": "ok", "mode": "analysis", "version": pipeline.VERSION}


@app.get("/api/config")
def config():
    from saqrsight.analysis.models import load_calibration
    return {
        "limits": cfg.public_limits(),
        "checks": {
            "text_analysis": True,
            "media_analysis": cfg.enable_models,
            "consistency_check": cfg.enable_models and load_calibration("consistency_classifier.json") is not None,
            "reverse_image_search": cfg.reverse_search_configured,
            "official_sources": cfg.official_search_configured,
        },
        "external": {
            "reverse_image_search": "Google Cloud Vision (the stored image, or up to "
                                    f"{cfg.max_reverse_frames} sampled video frames, without metadata)",
            "official_sources": f"{cfg.search_provider} search (event, place and date keywords only)",
            "official_domains": cfg.official_domains,
        },
    }


@app.post("/api/reports", status_code=202)
async def create_report(caption: str = Form(""), language: str = Form("auto"),
                        allow_external: bool = Form(False),
                        image: UploadFile | None = File(None), media: UploadFile | None = File(None)):
    upload = media if (media is not None and media.filename) else image
    original = caption.strip()
    if len(original) > cfg.max_text_chars:
        raise HTTPException(422, f"Text must be {cfg.max_text_chars:,} characters or fewer.")
    if language not in {"auto", "ar", "en", "mixed"}:
        raise HTTPException(422, "Choose Arabic, English, mixed, or automatic language selection.")
    has_file = upload is not None and bool(upload.filename)
    if not original and not has_file:
        raise HTTPException(422, "Enter text or upload an image or video.")
    rid = str(uuid.uuid4())
    info = None
    if has_file:
        limit = max(cfg.max_image_bytes, cfg.max_video_bytes)
        try:
            raw = await upload.read(limit + 1)
        finally:
            await upload.close()
        if len(raw) > limit:
            raise HTTPException(413, "The file is larger than the upload limits.")
        info = process_upload(raw, upload.filename, store.media_folder(rid), cfg)
    detected = detect_language(original) if original else "not applicable"
    chosen = detected if language == "auto" else language
    now = datetime.now(timezone.utc).isoformat()
    details = claims.extract(original) if original else claims.ClaimDetails()
    p = {"id": rid, "created_at": now, "status": "processing", "mode": "analysis", "version": pipeline.VERSION,
         "caption": original, "language": chosen, "language_detected": detected,
         "language_overridden": language != "auto", "media": info.public() if info else None,
         "consent_external": bool(allow_external), "claim_details": details.to_dict(), "modules": {},
         "notice": "Initial assessment generated by automated checks. It supports, but does not replace, human "
                   "verification. Findings marked 'not configured' or 'failed' were not assessed."}
    p["sections"] = report.build_sections(p)
    try:
        store.create(p, {"caption": original, "language": chosen, "language_detected": detected,
                         "media_kind": info.kind if info else None, "media_meta": p["media"],
                         "allow_external": bool(allow_external)})
    except Exception:
        import shutil
        shutil.rmtree(store.media_folder(rid), ignore_errors=True)
        raise
    pipeline.submit(store, cfg, p, info)
    return p


@app.get("/api/reports")
def history():
    return store.list(100)


def _view(p: dict) -> dict:
    """Rebuild display sections from the stored module results, so reports saved by earlier versions
    get the current bilingual wording. Findings, assessment and sources are never changed."""
    if p.get("mode") != "sample" and p.get("modules") is not None:
        p["sections"] = report.build_sections(p)
        if p.get("assessment"):
            from saqrsight.plain import plain_summary
            p["plain"] = plain_summary(p)
    return p


def _thumbnails(report_id: str, p: dict) -> list[dict]:
    """Small JPEG copies of the stored image / frames, embedded in the HTML export."""
    import base64
    from io import BytesIO
    from PIL import Image
    out = []
    for v in ((p.get("media") or {}).get("visuals") or [])[:6]:
        path = store.visual_path(report_id, v["ref"])
        if path is None:
            continue
        with Image.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail((520, 360))
            buf = BytesIO()
            im.save(buf, "JPEG", quality=80)
        out.append({"ref": v["ref"], "timestamp": v.get("timestamp"),
                    "uri": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()})
    return out


@app.get("/api/reports/{report_id}")
def read_report(report_id: str):
    return JSONResponse(_view(_record(report_id)), headers=NO_STORE)


@app.get("/api/reports/{report_id}/media/{ref}")
def read_media(report_id: str, ref: str):
    _record(report_id)
    path = store.visual_path(report_id, ref)
    if path is None:
        raise HTTPException(404, "Media not found.")
    return FileResponse(path, media_type="image/jpeg", headers=NO_STORE)


@app.get("/api/reports/{report_id}/image")
def read_image(report_id: str):
    p = _record(report_id)
    visuals = (p.get("media") or {}).get("visuals") or [{"ref": "image"}]
    return read_media(report_id, visuals[0]["ref"])


@app.get("/api/reports/{report_id}/download")
def download(report_id: str, format: str = "html", lang: str = "both"):
    p = _view(_record(report_id))
    if lang not in ("en", "ar", "both"):
        raise HTTPException(422, "Supported report languages: en, ar, both.")
    name = f"SaqrSight-{report_id}" + ("" if lang == "both" else f"-{lang}")
    if format == "json":
        return Response(json.dumps(p, ensure_ascii=False, indent=2), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{name}.json"'})
    if format != "html":
        raise HTTPException(422, "Supported formats: html, json.")
    return Response(report.render_html(p, _thumbnails(report_id, p), lang), media_type="text/html",
                    headers={"Content-Disposition": f'attachment; filename="{name}.html"'})


@app.delete("/api/reports/{report_id}", status_code=204)
def delete_report(report_id: str):
    if not store.delete(report_id):
        raise HTTPException(404, "Report not found.")
    return Response(status_code=204)
