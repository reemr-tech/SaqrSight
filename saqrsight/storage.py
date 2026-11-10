"""SQLite storage for submissions, module outputs, source references and final reports.

Schema (local prototype):
  reports         one row per report; `payload` holds the full report JSON shown to the user.
                  Legacy SGP1 sample reports live here with mode="sample" and image_name set.
  submissions     submission metadata (caption, language, media description, consent flag).
  module_results  one row per analysis module / evidence provider result.
  sources         every external source reference cited in a report (only provider-returned URLs).
  users           local accounts (name, email, PBKDF2 password hash – never the password itself).
  sessions        login sessions; only a SHA-256 hash of each session token is stored.
Every report belongs to one user (reports.user_id); users can only list, open, download or delete
their own reports. Reports saved before accounts existed are adopted by the first account created.
Deleting a report removes all four kinds of report rows and its media folder.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from .analysis.text_indicators import panic_level_of
from .config import Settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY, created_at TEXT, payload TEXT NOT NULL, image_name TEXT);
CREATE TABLE IF NOT EXISTS submissions (
    report_id TEXT PRIMARY KEY REFERENCES reports(id) ON DELETE CASCADE,
    caption TEXT, language TEXT, language_detected TEXT, media_kind TEXT,
    media_meta TEXT, allow_external INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS module_results (
    report_id TEXT REFERENCES reports(id) ON DELETE CASCADE, module TEXT, status TEXT,
    payload TEXT NOT NULL, PRIMARY KEY (report_id, module));
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id TEXT REFERENCES reports(id) ON DELETE CASCADE, module TEXT, url TEXT,
    title TEXT, relation TEXT, payload TEXT);
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL, expires_at TEXT NOT NULL);
"""
MIGRATIONS = [
    ("reports", "status", "ALTER TABLE reports ADD COLUMN status TEXT NOT NULL DEFAULT 'complete'"),
    ("reports", "media_dir", "ALTER TABLE reports ADD COLUMN media_dir TEXT"),
    ("reports", "updated_at", "ALTER TABLE reports ADD COLUMN updated_at TEXT"),
    ("reports", "user_id", "ALTER TABLE reports ADD COLUMN user_id TEXT"),
]


class Store:
    def __init__(self, cfg: Settings):
        self.cfg = cfg
        cfg.media_dir.mkdir(parents=True, exist_ok=True)
        with self.db() as con:
            con.executescript(SCHEMA)
            for table, column, sql in MIGRATIONS:
                cols = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
                if column not in cols:
                    con.execute(sql)

    @contextmanager
    def db(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.cfg.db_path, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        try:
            yield con
            con.commit()
        finally:
            con.close()

    def media_folder(self, report_id: str) -> Path:
        return self.cfg.media_dir / report_id

    # --- writes -----------------------------------------------------------------------------
    def create(self, payload: dict, submission: dict, user_id: str | None = None) -> None:
        with self.db() as con:
            con.execute("INSERT INTO reports (id, created_at, payload, image_name, status, media_dir, updated_at, "
                        "user_id) VALUES (?,?,?,?,?,?,?,?)",
                        (payload["id"], payload["created_at"], _dump(payload), None, payload["status"],
                         payload["id"] if submission.get("media_kind") else None, payload["created_at"], user_id))
            con.execute("INSERT INTO submissions VALUES (?,?,?,?,?,?,?)",
                        (payload["id"], submission["caption"], submission["language"],
                         submission["language_detected"], submission.get("media_kind"),
                         _dump(submission.get("media_meta")), int(submission.get("allow_external", False))))

    def save_module(self, report_id: str, result: dict) -> None:
        with self.db() as con:
            con.execute("INSERT OR REPLACE INTO module_results VALUES (?,?,?,?)",
                        (report_id, result["module"], result["status"], _dump(result)))
            con.execute("DELETE FROM sources WHERE report_id=? AND module=?", (report_id, result["module"]))
            for f in result.get("findings", []):
                for s in f.get("sources", []):
                    con.execute("INSERT INTO sources (report_id, module, url, title, relation, payload) "
                                "VALUES (?,?,?,?,?,?)",
                                (report_id, result["module"], s.get("url"), s.get("title"),
                                 s.get("relation"), _dump(s)))

    def update_payload(self, payload: dict) -> None:
        with self.db() as con:
            con.execute("UPDATE reports SET payload=?, status=?, updated_at=? WHERE id=?",
                        (_dump(payload), payload.get("status", "complete"), _now(), payload["id"]))

    def delete(self, report_id: str) -> bool:
        row = self.get_row(report_id)
        if row is None:
            return False
        with self.db() as con:
            con.execute("DELETE FROM reports WHERE id=?", (report_id,))
            # Explicit deletes as well, in case foreign keys were disabled when rows were written.
            for table in ("submissions", "module_results", "sources"):
                con.execute(f"DELETE FROM {table} WHERE report_id=?", (report_id,))
        self._delete_media(row)
        return True

    def _delete_media(self, row: sqlite3.Row) -> None:
        if row["image_name"]:  # legacy SGP1 layout: data/media/<id>.jpg
            (self.cfg.media_dir / Path(row["image_name"]).name).unlink(missing_ok=True)
        folder = self.media_folder(row["id"])
        if folder.is_dir():
            shutil.rmtree(folder, ignore_errors=True)

    def purge_expired(self) -> int:
        if self.cfg.retention_days <= 0:
            return 0
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.cfg.retention_days)).isoformat()
        with self.db() as con:
            ids = [r["id"] for r in con.execute("SELECT id FROM reports WHERE created_at < ?", (cutoff,))]
        for rid in ids:
            self.delete(rid)
        return len(ids)

    # --- reads ------------------------------------------------------------------------------
    def get_row(self, report_id: str) -> sqlite3.Row | None:
        with self.db() as con:
            return con.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()

    def get(self, report_id: str) -> dict | None:
        row = self.get_row(report_id)
        return json.loads(row["payload"]) if row else None

    def modules(self, report_id: str) -> list[dict]:
        with self.db() as con:
            return [json.loads(r["payload"]) for r in
                    con.execute("SELECT payload FROM module_results WHERE report_id=?", (report_id,))]

    def list(self, limit: int = 100, user_id: str | None = None, q: str = "", verdict: str = "",
             priority: str = "", language: str = "", panic: str = "") -> list[dict]:
        """Summaries of a user's reports, newest first, optionally filtered (used by Search reports)."""
        with self.db() as con:
            if user_id is None:
                rows = con.execute("SELECT id, created_at, payload, status FROM reports "
                                   "ORDER BY created_at DESC").fetchall()
            else:
                rows = con.execute("SELECT id, created_at, payload, status FROM reports WHERE user_id=? "
                                   "ORDER BY created_at DESC", (user_id,)).fetchall()
        out = []
        needle = _fold(q)
        for r in rows:
            item = _summary(r)
            if needle and needle not in _fold(item["caption"]):
                continue
            if verdict and item["assessment"] != verdict:
                continue
            if priority and item["priority"] != priority:
                continue
            if language and item["language"] != language:
                continue
            if panic and item["panic_level"] != panic:
                continue
            out.append(item)
            if len(out) >= limit:
                break
        return out

    def dashboard(self, user_id: str) -> dict:
        """Counts for the dashboard, computed from the user's saved reports."""
        items = self.list(limit=10_000, user_id=user_id)
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        count = lambda key, values: {v: sum(1 for i in items if i[key] == v) for v in values}  # noqa: E731
        analysed = [i for i in items if i["mode"] != "sample" and i["status"] == "complete"]
        return {
            "total": len(items),
            "this_week": sum(1 for i in items if i["created_at"] >= week_ago),
            "verdicts": count("assessment", ["potentially_misleading", "insufficient_evidence", "apparently_consistent"]),
            "priorities": count("priority", ["high", "medium", "low"]),
            "panic_levels": count("panic_level", ["strong", "mild", "none"]),
            "languages": count("language", ["ar", "en", "mixed"]),
            "categories": {c: sum(1 for i in analysed if c in i["categories"])
                           for c in ("urgency", "fear", "manipulation", "share_pressure")},
            "analysed": len(analysed),
            "samples": sum(1 for i in items if i["mode"] == "sample"),
            "recent": items[:5],
        }

    # --- users and sessions -----------------------------------------------------------------
    def create_user(self, user_id: str, name: str, email: str, password_hash: str) -> bool:
        """Create an account; the very first account adopts reports saved before accounts existed."""
        with self.db() as con:
            first = con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
            try:
                con.execute("INSERT INTO users (id, name, email, password_hash, created_at) VALUES (?,?,?,?,?)",
                            (user_id, name, email, password_hash, _now()))
            except sqlite3.IntegrityError:
                return False
            if first:
                con.execute("UPDATE reports SET user_id=? WHERE user_id IS NULL", (user_id,))
        return True

    def user_by_email(self, email: str) -> sqlite3.Row | None:
        with self.db() as con:
            return con.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()

    def create_session(self, token_hash: str, user_id: str, days: int) -> None:
        now = datetime.now(timezone.utc)
        with self.db() as con:
            con.execute("DELETE FROM sessions WHERE expires_at < ?", (now.isoformat(),))
            con.execute("INSERT INTO sessions VALUES (?,?,?,?)",
                        (token_hash, user_id, now.isoformat(), (now + timedelta(days=days)).isoformat()))

    def user_for_session(self, token_hash: str) -> dict | None:
        with self.db() as con:
            row = con.execute("SELECT u.id, u.name, u.email FROM sessions s JOIN users u ON u.id = s.user_id "
                              "WHERE s.token_hash=? AND s.expires_at > ?", (token_hash, _now())).fetchone()
        return dict(row) if row else None

    def delete_session(self, token_hash: str) -> None:
        with self.db() as con:
            con.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))

    def owner(self, report_id: str) -> str | None:
        row = self.get_row(report_id)
        return row["user_id"] if row else None

    def visual_path(self, report_id: str, ref: str) -> Path | None:
        row = self.get_row(report_id)
        if row is None:
            return None
        if row["image_name"] and ref == "image":
            p = self.cfg.media_dir / Path(row["image_name"]).name
            return p if p.is_file() else None
        if not ref.replace("-", "").isalnum():
            return None
        p = self.media_folder(report_id) / f"{ref}.jpg"
        return p if p.is_file() else None


def _summary(r: sqlite3.Row) -> dict:
    p = json.loads(r["payload"])
    media = p.get("media") or ({"kind": "image"} if p.get("image") else None)
    t = (p.get("modules") or {}).get("text_analysis") or {}
    text = t.get("data") or {}
    return {"id": r["id"], "created_at": r["created_at"], "caption": p.get("caption", ""),
            "mode": p.get("mode", "analysis"), "status": r["status"], "language": p.get("language"),
            "has_image": bool(media), "media_kind": media and media.get("kind"),
            "assessment": (p.get("assessment") or {}).get("verdict"),
            "priority": (p.get("priority") or {}).get("level"),
            "panic_level": panic_level_of(text) if t.get("status") == "completed" else None, "categories": text.get("categories", [])}


def _fold(text: str) -> str:
    """Case- and Arabic-letter-insensitive form for searching (أ/إ/آ→ا, ة→ه, ى→ي, no diacritics)."""
    from .textutil import normalize
    return normalize(text or "")


def _dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
