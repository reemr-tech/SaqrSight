"""End-to-end API workflow: submission, validation, processing, reports, exports, deletion."""
import json
import sqlite3
from io import BytesIO

import pytest
from PIL import Image

from conftest import mp4, png, wait


def test_page_assets_and_config(client):
    assert "SaqrSight" in client.get("/").text
    for asset in ("app.js", "style.css", "report.css", "i18n.js", "falcon.svg", "motion.js", "motion.css",
                  "vendor/gsap.min.js", "vendor/ScrollTrigger.min.js", "vendor/SplitText.min.js",
                  "vendor/lenis.min.js", "vendor/lenis.css"):
        assert client.get("/static/" + asset).status_code == 200
    cfg = client.get("/api/config").json()
    assert cfg["limits"]["max_text_chars"] == 10000 and cfg["limits"]["max_video_seconds"] == 60
    assert cfg["checks"]["reverse_image_search"] is False and cfg["checks"]["official_sources"] is False


@pytest.mark.parametrize("caption,lang", [("A claim about Dubai", "en"), ("خبر عن دبي اليوم", "ar"),
                                          ("عاجل breaking news in دبي now اليوم", "mixed")])
def test_text_only(client, caption, lang):
    r = client.post("/api/reports", data={"caption": caption})
    assert r.status_code == 202 and r.json()["status"] == "processing"
    p = wait(client, r.json()["id"])
    assert p["caption"] == caption and p["language"] == lang and p["mode"] == "analysis"
    m = p["modules"]
    assert m["text_analysis"]["status"] == "completed"
    assert m["media_analysis"]["status"] == "not_applicable"
    assert m["consistency_check"]["status"] == "not_applicable"
    assert m["official_sources"]["status"] == "not_configured"
    assert [s["key"] for s in p["sections"]] == [
        "initial_assessment", "confidence", "text_analysis", "media_analysis", "consistency_check", "issue_type",
        "review_priority", "panic_language", "previous_media", "official_sources", "recommended_action"]
    assert p["assessment"]["verdict"] == "insufficient_evidence"
    assert client.get("/api/reports").json()[0]["id"] == p["id"]


def test_language_override(client):
    p = wait(client, client.post("/api/reports", data={"caption": "Dubai", "language": "ar"}).json()["id"])
    assert p["language"] == "ar" and p["language_detected"] == "en" and p["language_overridden"]


def test_image_only_and_combined(client):
    p = wait(client, client.post("/api/reports", files={"media": ("x.png", png(), "image/png")}).json()["id"])
    assert p["language"] == "not applicable"
    assert p["modules"]["text_analysis"]["status"] == "not_applicable"
    # models are switched off in this fixture: visible as "not configured", never as a result
    assert p["modules"]["media_analysis"]["status"] == "not_configured"
    assert p["assessment"]["rule"] == "A4"
    # SGP1 field name "image" still accepted
    r = client.post("/api/reports", data={"caption": "دبي"}, files={"image": ("../../photo.png", png(), "image/png")})
    p = wait(client, r.json()["id"])
    assert p["media"]["original_name"] == "photo.png" and p["media"]["kind"] == "image"
    img = client.get(f"/api/reports/{p['id']}/media/image")
    assert img.headers["content-type"] == "image/jpeg" and Image.open(BytesIO(img.content)).size == (64, 48)
    assert client.get(f"/api/reports/{p['id']}/image").status_code == 200
    assert client.get(f"/api/reports/{p['id']}/media/..%2F..%2Fsaqrsight").status_code == 404


def test_video_frames(client, tmp_path):
    raw = mp4(tmp_path / "clip.mp4", seconds=4)
    p = wait(client, client.post("/api/reports", data={"caption": "Fire in Sharjah"},
                                  files={"media": ("clip.mp4", raw, "video/mp4")}).json()["id"])
    media = p["media"]
    assert media["kind"] == "video" and abs(media["duration"] - 4) < 0.2
    ts = [v["timestamp"] for v in media["visuals"]]
    assert len(ts) == 5 and ts == sorted(ts) and 0 < ts[0] < ts[-1] < 4
    for v in media["visuals"]:
        assert client.get(f"/api/reports/{p['id']}/media/{v['ref']}").status_code == 200
    html = client.get(f"/api/reports/{p['id']}/download?format=html").text
    assert "findings apply to sampled frames" in html
    # the original video bytes are not kept
    folder = client.app_module.MEDIA / p["id"]
    assert sorted(f.name for f in folder.iterdir()) == [f"frame-{i}.jpg" for i in range(1, 6)]


def test_video_too_long(client, tmp_path, monkeypatch):
    raw = mp4(tmp_path / "long.mp4", seconds=3)
    monkeypatch.setattr(client.app_module.cfg, "max_video_seconds", 2.0)
    r = client.post("/api/reports", files={"media": ("long.mp4", raw, "video/mp4")})
    assert r.status_code == 413 and "seconds" in r.json()["detail"]
    assert client.get("/api/reports").json() == []
    assert not any(client.app_module.MEDIA.iterdir())


@pytest.mark.parametrize("data", [{}, {"caption": "  "}, {"caption": "x" * 10001}, {"caption": "x", "language": "xx"}])
def test_bad_forms(client, data):
    assert client.post("/api/reports", data=data).status_code == 422
    assert client.get("/api/reports").json() == []


def test_invalid_uploads(client):
    bad = [("fake.png", b"<script>x</script>", 415), ("big.png", b"x" * (60 * 1024 * 1024 + 1), 413),
           ("empty.png", b"", 422), ("fake.mp4", b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 200, 415)]
    for name, raw, code in bad:
        r = client.post("/api/reports", files={"media": (name, raw, "application/octet-stream")})
        assert r.status_code == code, (name, r.text)
        assert r.json()["detail"]
    buf = BytesIO(); Image.new("RGB", (20, 20)).save(buf, "GIF")
    assert client.post("/api/reports", files={"media": ("x.gif", buf.getvalue(), "image/gif")}).status_code == 415
    buf = BytesIO(); Image.new("L", (5000, 4001)).save(buf, "PNG")
    assert client.post("/api/reports", files={"media": ("huge.png", buf.getvalue(), "image/png")}).status_code == 415
    assert client.post("/api/reports", files={"media": ("tiny.png", png((10, 10)), "image/png")}).status_code == 422
    big_jpeg = BytesIO(); Image.effect_noise((2000, 2000), 100).convert("RGB").save(big_jpeg, "PNG")
    if len(big_jpeg.getvalue()) > 10 * 1024 * 1024:
        assert client.post("/api/reports", files={"media": ("b.png", big_jpeg.getvalue(), "image/png")}).status_code == 413
    assert client.get("/api/reports").json() == []


def test_exports_escape_and_delete(client):
    caption = "<script>alert(1)</script> دبي"
    p = wait(client, client.post("/api/reports", data={"caption": caption},
                                  files={"media": ("x.png", png(), "image/png")}).json()["id"])
    url = "/api/reports/" + p["id"]
    html = client.get(url + "/download?format=html")
    assert "<script>alert(1)</script>" not in html.text and "&lt;script&gt;" in html.text and "دبي" in html.text
    for label in ("Initial Assessment", "التقييم الأولي", "Not configured", "Review Priority", "Recommended Action"):
        assert label in html.text
    assert "attachment" in html.headers["content-disposition"]
    assert client.get(url + "/download?format=json").json() == p
    assert client.get(url + "/download?format=exe").status_code == 422
    db = client.app_module.cfg.db_path
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT COUNT(*) FROM module_results WHERE report_id=?", (p["id"],)).fetchone()[0] == 5
        assert con.execute("SELECT COUNT(*) FROM submissions WHERE report_id=?", (p["id"],)).fetchone()[0] == 1
    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404 and client.get(url + "/image").status_code == 404
    assert client.get("/api/reports").json() == []
    assert not any(client.app_module.MEDIA.iterdir())
    with sqlite3.connect(db) as con:
        for table in ("reports", "submissions", "module_results", "sources"):
            assert con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_persistence_and_missing(client):
    import importlib
    from fastapi.testclient import TestClient
    p = wait(client, client.post("/api/reports", data={"caption": "Persistent report"}).json()["id"])
    app = client.app_module
    importlib.reload(app)
    with TestClient(app.app) as second:
        assert second.get("/api/reports/" + p["id"]).json()["caption"] == "Persistent report"
    assert client.get("/api/reports/missing").status_code == 404
    assert client.delete("/api/reports/missing").status_code == 404


def test_legacy_sample_reports_remain_labelled(client):
    """Reports saved by the SGP1 prototype (old schema, flat media files) still open, export and delete."""
    app = client.app_module
    rid = "a90aef42-b004-4d93-ab86-e8ee904db168"
    payload = {"id": rid, "created_at": "2099-01-01T00:00:00+00:00", "mode": "sample", "caption": "عاجل",
               "language": "ar", "image": {"width": 64, "height": 48, "original_name": "x.png"},
               "notice": "WORKFLOW DEMONSTRATION ONLY. All analytical findings are placeholders, not AI results.",
               "sections": [{"title": "Overall assessment", "finding": "Sample only"}]}
    Image.open(BytesIO(png())).save(app.MEDIA / f"{rid}.jpg")
    with sqlite3.connect(app.cfg.db_path) as con:
        con.execute("INSERT INTO reports (id, created_at, payload, image_name) VALUES (?,?,?,?)",
                    (rid, payload["created_at"], json.dumps(payload, ensure_ascii=False), f"{rid}.jpg"))
    row = client.get("/api/reports").json()[0]
    assert row["mode"] == "sample" and row["has_image"]
    assert client.get(f"/api/reports/{rid}/image").status_code == 200
    assert "WORKFLOW DEMONSTRATION ONLY" in client.get(f"/api/reports/{rid}/download?format=html").text
    assert client.delete(f"/api/reports/{rid}").status_code == 204
    assert not (app.MEDIA / f"{rid}.jpg").exists()


def test_failed_module_still_produces_report(client, monkeypatch):
    from saqrsight.analysis import text_indicators

    def boom(*a, **k):
        raise RuntimeError("model crashed with user text inside")
    monkeypatch.setattr(text_indicators, "analyze", boom)
    p = wait(client, client.post("/api/reports", data={"caption": "Fire in Dubai today"}).json()["id"])
    t = p["modules"]["text_analysis"]
    assert t["status"] == "failed" and t["error"] == "RuntimeError"   # no user content in errors
    assert p["assessment"]["verdict"] == "insufficient_evidence"
    sec = next(s for s in p["sections"] if s["key"] == "text_analysis")
    assert sec["status"] == "failed"


def test_module_timeout_keeps_other_results(client, monkeypatch):
    import time as _t
    from saqrsight.analysis import visual
    monkeypatch.setattr(client.app_module.cfg, "module_timeout", 0.3)

    def slow(*a, **k):
        _t.sleep(1)
    monkeypatch.setattr(visual, "analyze", slow)
    p = wait(client, client.post("/api/reports", data={"caption": "Dubai"},
                                  files={"media": ("x.png", png(), "image/png")}).json()["id"])
    assert p["modules"]["media_analysis"]["status"] == "failed"
    assert "Timed out" in p["modules"]["media_analysis"]["error"]
    assert p["modules"]["text_analysis"]["status"] == "completed"


def test_retention_purge(tmp_path, monkeypatch):
    monkeypatch.setenv("SAQRSIGHT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SAQRSIGHT_RETENTION_DAYS", "1")
    from saqrsight.config import settings
    from saqrsight.storage import Store
    store = Store(settings())
    old = {"id": "old", "created_at": "2000-01-01T00:00:00+00:00", "status": "complete"}
    new = {"id": "new", "created_at": "2999-01-01T00:00:00+00:00", "status": "complete"}
    for p in (old, new):
        store.create(p, {"caption": "", "language": "", "language_detected": "", "media_kind": "image"})
        store.media_folder(p["id"]).mkdir(parents=True)
    assert store.purge_expired() == 1
    assert store.get("old") is None and store.get("new") is not None
    assert not store.media_folder("old").exists()
