"""Accounts: signup, login, logout, session security and per-user report isolation."""
import sqlite3

from fastapi.testclient import TestClient

from conftest import wait


def test_signup_validation_and_duplicates(client):
    for body, code in [({"name": "", "email": "a@b.co", "password": "longenough"}, 422),
                       ({"name": "A", "email": "not-an-email", "password": "longenough"}, 422),
                       ({"name": "A", "email": "a@b.co", "password": "short"}, 422),
                       ({"name": "A", "email": "TEST@example.com", "password": "longenough"}, 409)]:
        assert client.post("/api/auth/signup", json=body).status_code == code


def test_password_is_hashed_not_stored(client):
    with sqlite3.connect(client.app_module.cfg.db_path) as con:
        stored = con.execute("SELECT password_hash FROM users WHERE email='test@example.com'").fetchone()[0]
        token = con.execute("SELECT token_hash FROM sessions").fetchone()[0]
    assert "correct horse" not in stored and stored.startswith("pbkdf2_sha256$310000$")
    assert token != client.cookies.get("saqr_session")          # only the hash of the session token is kept


def test_login_logout_and_protection(client):
    assert client.get("/api/auth/me").json()["email"] == "test@example.com"
    assert client.post("/api/auth/logout").status_code == 204
    for url in ("/api/auth/me", "/api/reports", "/api/dashboard"):
        assert client.get(url).status_code == 401
    assert client.post("/api/reports", data={"caption": "x"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "test@example.com", "password": "wrong password"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": " Test@Example.com ", "password": "correct horse 1"})
    assert r.status_code == 200 and client.get("/api/auth/me").status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_login_throttling(client):
    for _ in range(5):
        client.post("/api/auth/login", json={"email": "test@example.com", "password": "bad guess"})
    r = client.post("/api/auth/login", json={"email": "test@example.com", "password": "correct horse 1"})
    assert r.status_code == 429


def test_users_only_see_their_own_reports(client):
    mine = wait(client, client.post("/api/reports", data={"caption": "My private report"}).json()["id"])
    other = TestClient(client.app_module.app)
    assert other.post("/api/auth/signup", json={"name": "Other", "email": "other@example.com",
                                                "password": "another pass 2"}).status_code == 201
    assert other.get("/api/reports").json() == []
    for path in ("", "/download?format=html", "/download?format=json"):
        assert other.get(f"/api/reports/{mine['id']}{path}").status_code == 404
    assert other.delete(f"/api/reports/{mine['id']}").status_code == 404
    assert other.get("/api/dashboard").json()["total"] == 0
    assert client.get(f"/api/reports/{mine['id']}").status_code == 200   # still there for its owner


def test_search_and_dashboard(client):
    a = wait(client, client.post("/api/reports", data={"caption": "عاجل دزوها! الناس محاصرين في دبي"}).json()["id"])
    b = wait(client, client.post("/api/reports", data={"caption": "Traffic is normal on Emirates Road"}).json()["id"])
    assert [r["id"] for r in client.get("/api/reports", params={"q": "traffic"}).json()] == [b["id"]]
    assert [r["id"] for r in client.get("/api/reports", params={"q": "دبى"}).json()] == [a["id"]]   # ى/ي folded
    assert [r["id"] for r in client.get("/api/reports", params={"language": "ar"}).json()] == [a["id"]]
    assert [r["id"] for r in client.get("/api/reports", params={"panic": "strong"}).json()] == [a["id"]]
    d = client.get("/api/dashboard").json()
    assert d["total"] == 2 and d["languages"]["ar"] == 1 and d["panic_levels"]["strong"] == 1
    assert d["categories"]["share_pressure"] == 1 and len(d["recent"]) == 2


def test_first_account_adopts_older_reports(tmp_path, monkeypatch):
    import importlib
    import json
    monkeypatch.setenv("SAQRSIGHT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SAQRSIGHT_ENABLE_MODELS", "0")
    import app
    importlib.reload(app)
    payload = {"id": "old-1", "created_at": "2099-01-01T00:00:00+00:00", "mode": "sample", "caption": "old",
               "language": "en", "image": None, "notice": "", "sections": []}
    with sqlite3.connect(app.cfg.db_path) as con:
        con.execute("INSERT INTO reports (id, created_at, payload) VALUES (?,?,?)",
                    ("old-1", payload["created_at"], json.dumps(payload)))
    with TestClient(app.app) as c:
        c.post("/api/auth/signup", json={"name": "First", "email": "first@example.com", "password": "first pass 1"})
        assert [r["id"] for r in c.get("/api/reports").json()] == ["old-1"]


def test_sgp1_default_text_only(tmp_path, monkeypatch):
    """By default (Senior Project 1) image and video analysis is off: uploads are refused, text works."""
    import importlib
    from conftest import png
    monkeypatch.setenv("SAQRSIGHT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SAQRSIGHT_ENABLE_MODELS", "0")
    monkeypatch.delenv("SAQRSIGHT_MEDIA_ENABLED", raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as c:
        cfg = c.get("/api/config").json()
        assert cfg["media_enabled"] is False and cfg["checks"]["media_analysis"] is False
        c.post("/api/auth/signup", json={"name": "A", "email": "a@example.com", "password": "pass word 1"})
        r = c.post("/api/reports", data={"caption": "Fire in Dubai"}, files={"media": ("x.png", png(), "image/png")})
        assert r.status_code == 422 and "Senior Project 2" in r.json()["detail"]
        assert c.get("/api/reports").json() == []
        assert wait(c, c.post("/api/reports", data={"caption": "Fire in Dubai"}).json()["id"])["status"] == "complete"
