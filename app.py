"""SaqrSight SGP2: FastAPI entry point.

Operations (all /api/reports and /api/dashboard routes require a signed-in user and only ever
return that user's own reports)
  POST   /api/auth/signup | /api/auth/login | /api/auth/logout ;  GET /api/auth/me
  GET    /api/config                         upload limits and which optional checks are available
  GET    /api/dashboard                      counts for the dashboard (verdicts, priorities, panic levels ...)
  POST   /api/reports                        submit caption and/or one image or short video (202, processing)
  GET    /api/reports?q=&verdict=&priority=&language=&panic=   search saved reports (most recent first)
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

from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from saqrsight import auth, pipeline, report
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
throttle = auth.Throttle()


@app.exception_handler(SubmissionError)
def _submission_error(_: Request, e: SubmissionError):
    return JSONResponse({"detail": e.message, "code": e.code}, status_code=e.status)


def current_user(request: Request) -> dict:
    token = request.cookies.get(auth.SESSION_COOKIE)
    user = store.user_for_session(auth.token_hash(token)) if token else None
    if user is None:
        raise HTTPException(401, "Please log in.")
    return user


def _record(report_id: str, user: dict) -> dict:
    """A report the signed-in user owns. Someone else's report gives the same 404 as a missing one."""
    p = store.get(report_id)
    if p is None or store.owner(report_id) != user["id"]:
        raise HTTPException(404, "Report not found.")
    return p


def _start_session(response: Response, user_id: str) -> None:
    token = auth.new_token()
    store.create_session(auth.token_hash(token), user_id, auth.SESSION_DAYS)
    response.set_cookie(auth.SESSION_COOKIE, token, max_age=auth.SESSION_DAYS * 86400, httponly=True,
                        samesite="lax", secure=cfg.secure_cookies, path="/")


# ---- accounts ------------------------------------------------------------------------------
@app.post("/api/auth/signup", status_code=201)
def signup(response: Response, name: str = Body(""), email: str = Body(""), password: str = Body("")):
    error = auth.validate_signup(name, email, password)
    if error:
        raise HTTPException(422, error)
    user_id = str(uuid.uuid4())
    if not store.create_user(user_id, name.strip(), auth.normalize_email(email), auth.hash_password(password)):
        raise HTTPException(409, "An account with this email already exists. Please log in.")
    _start_session(response, user_id)
    return {"id": user_id, "name": name.strip(), "email": auth.normalize_email(email)}


@app.post("/api/auth/login")
def login(response: Response, email: str = Body(""), password: str = Body("")):
    key = auth.normalize_email(email)
    if throttle.blocked(key):
        raise HTTPException(429, "Too many failed attempts. Please wait a few minutes and try again.")
    row = store.user_by_email(key)
    if row is None or not auth.verify_password(password, row["password_hash"]):
        throttle.fail(key)
        raise HTTPException(401, "Email or password is incorrect.")
    throttle.reset(key)
    _start_session(response, row["id"])
    return {"id": row["id"], "name": row["name"], "email": row["email"]}


@app.post("/api/auth/logout", status_code=204)
def logout(request: Request):
    token = request.cookies.get(auth.SESSION_COOKIE)
    if token:
        store.delete_session(auth.token_hash(token))
    response = Response(status_code=204)
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return response


@app.get("/api/auth/me")
def me(user: dict = Depends(current_user)):
    return user


@app.get("/api/dashboard")
def dashboard(user: dict = Depends(current_user)):
    return JSONResponse(store.dashboard(user["id"]), headers=NO_STORE)


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
        "media_enabled": cfg.media_enabled,
        "checks": {
            "text_analysis": True,
            "media_analysis": cfg.media_enabled and cfg.enable_models,
            "consistency_check": cfg.media_enabled and cfg.enable_models
                                 and load_calibration("consistency_classifier.json") is not None,
            "reverse_image_search": cfg.media_enabled and cfg.reverse_search_configured,
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
                        image: UploadFile | None = File(None), media: UploadFile | None = File(None),
                        user: dict = Depends(current_user)):
    upload = media if (media is not None and media.filename) else image
    original = caption.strip()
    if len(original) > cfg.max_text_chars:
        raise HTTPException(422, f"Text must be {cfg.max_text_chars:,} characters or fewer.")
    if language not in {"auto", "ar", "en", "mixed"}:
        raise HTTPException(422, "Choose Arabic, English, mixed, or automatic language selection.")
    has_file = upload is not None and bool(upload.filename)
    if has_file and not cfg.media_enabled:
        raise HTTPException(422, "Image and video analysis is not available yet – it is planned for Senior "
                                 "Project 2. Please submit the post's text.")
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
                         "allow_external": bool(allow_external)}, user_id=user["id"])
    except Exception:
        import shutil
        shutil.rmtree(store.media_folder(rid), ignore_errors=True)
        raise
    pipeline.submit(store, cfg, p, info)
    return p


@app.get("/api/reports")
def history(q: str = "", verdict: str = "", priority: str = "", language: str = "", panic: str = "",
            user: dict = Depends(current_user)):
    return store.list(100, user_id=user["id"], q=q[:200], verdict=verdict, priority=priority,
                      language=language, panic=panic)


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
def read_report(report_id: str, user: dict = Depends(current_user)):
    return JSONResponse(_view(_record(report_id, user)), headers=NO_STORE)


@app.get("/api/reports/{report_id}/media/{ref}")
def read_media(report_id: str, ref: str, user: dict = Depends(current_user)):
    _record(report_id, user)
    path = store.visual_path(report_id, ref)
    if path is None:
        raise HTTPException(404, "Media not found.")
    return FileResponse(path, media_type="image/jpeg", headers=NO_STORE)


@app.get("/api/reports/{report_id}/image")
def read_image(report_id: str, user: dict = Depends(current_user)):
    p = _record(report_id, user)
    visuals = (p.get("media") or {}).get("visuals") or [{"ref": "image"}]
    return read_media(report_id, visuals[0]["ref"], user)


@app.get("/api/reports/{report_id}/download")
def download(report_id: str, format: str = "html", lang: str = "both", user: dict = Depends(current_user)):
    p = _view(_record(report_id, user))
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
def delete_report(report_id: str, user: dict = Depends(current_user)):
    _record(report_id, user)
    if not store.delete(report_id):
        raise HTTPException(404, "Report not found.")
    return Response(status_code=204)
