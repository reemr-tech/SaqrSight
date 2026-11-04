"""SQLite storage for submissions, module outputs, source references and final reports.

Schema (local prototype):
  reports         one row per report; `payload` holds the full report JSON shown to the user.
                  Legacy SGP1 sample reports live here with mode="sample" and image_name set.
  submissions     submission metadata (caption, language, media description, consent flag).
  module_results  one row per analysis module / evidence provider result.
  sources         every external source reference cited in a report (only provider-returned URLs).
Deleting a report removes all four kinds of rows and its media folder.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

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
"""
MIGRATIONS = [
    ("reports", "status", "ALTER TABLE reports ADD COLUMN status TEXT NOT NULL DEFAULT 'complete'"),
    ("reports", "media_dir", "ALTER TABLE reports ADD COLUMN media_dir TEXT"),
    ("reports", "updated_at", "ALTER TABLE reports ADD COLUMN updated_at TEXT"),
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
    def create(self, payload: dict, submission: dict) -> None:
        with self.db() as con:
            con.execute("INSERT INTO reports (id, created_at, payload, image_name, status, media_dir, updated_at) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (payload["id"], payload["created_at"], _dump(payload), None, payload["status"],
                         payload["id"] if submission.get("media_kind") else None, payload["created_at"]))
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

    def list(self, limit: int = 100) -> list[dict]:
        with self.db() as con:
            rows = con.execute("SELECT id, created_at, payload, status FROM reports "
                               "ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            p = json.loads(r["payload"])
            media = p.get("media") or ({"kind": "image"} if p.get("image") else None)
            out.append({"id": r["id"], "created_at": r["created_at"], "caption": p.get("caption", ""),
                        "mode": p.get("mode", "analysis"), "status": r["status"],
                        "has_image": bool(media), "media_kind": media and media.get("kind"),
                        "assessment": (p.get("assessment") or {}).get("verdict"),
                        "priority": (p.get("priority") or {}).get("level")})
        return out

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


def _dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
