from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  platform TEXT NOT NULL,
  external_id TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  url TEXT NOT NULL,
  budget_text TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL,
  score INTEGER NOT NULL DEFAULT 0,
  score_reasons TEXT NOT NULL DEFAULT '[]',
  discovered_at TEXT NOT NULL,
  UNIQUE(platform, external_id)
);
CREATE TABLE IF NOT EXISTS drafts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id INTEGER NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
  proposal TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('PENDING_REVIEW','APPROVED','REJECTED','RECORDED_SUBMITTED')),
  created_at TEXT NOT NULL,
  reviewed_at TEXT,
  submitted_at TEXT,
  reviewer_certified INTEGER NOT NULL DEFAULT 0,
  notes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  external_id TEXT NOT NULL UNIQUE,
  platform TEXT NOT NULL,
  subject TEXT NOT NULL,
  preview TEXT NOT NULL DEFAULT '',
  url TEXT NOT NULL DEFAULT '',
  received_at TEXT NOT NULL,
  notified_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn


@contextmanager
def session(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_job(conn: sqlite3.Connection, job: dict[str, Any]) -> tuple[int, bool]:
    existing = conn.execute(
        "SELECT id FROM jobs WHERE platform=? AND external_id=?",
        (job["platform"], job["external_id"]),
    ).fetchone()
    if existing:
        return int(existing["id"]), False
    cur = conn.execute(
        """INSERT INTO jobs(platform,external_id,title,description,url,budget_text,category,source,score,score_reasons,discovered_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (
            job["platform"], job["external_id"], job["title"], job.get("description", ""),
            job["url"], job.get("budget_text", ""), job.get("category", ""), job["source"],
            int(job.get("score", 0)), json.dumps(job.get("score_reasons", [])), job.get("discovered_at", utcnow()),
        ),
    )
    return int(cur.lastrowid), True


def create_draft(conn: sqlite3.Connection, job_id: int, proposal: str) -> int:
    cur = conn.execute(
        "INSERT INTO drafts(job_id,proposal,status,created_at) VALUES(?,?,?,?)",
        (job_id, proposal, "PENDING_REVIEW", utcnow()),
    )
    return int(cur.lastrowid)


def set_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def get_state(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
    return str(row["value"]) if row else default
