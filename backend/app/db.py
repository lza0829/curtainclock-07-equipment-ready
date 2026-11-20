from __future__ import annotations

import sqlite3
from contextlib import contextmanager

from app.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS rooms (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  capacity INTEGER NOT NULL,
  active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS teachers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  subject TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  subject TEXT NOT NULL,
  room_code TEXT NOT NULL,
  teacher_code TEXT NOT NULL,
  day TEXT NOT NULL,
  start_min INTEGER NOT NULL,
  end_min INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft',
  bypass INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS leases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lease_no TEXT NOT NULL UNIQUE,
  session_code TEXT NOT NULL,
  room_code TEXT NOT NULL,
  teacher_code TEXT NOT NULL,
  day TEXT NOT NULL,
  start_min INTEGER NOT NULL,
  end_min INTEGER NOT NULL,
  status TEXT NOT NULL,
  opened_at TEXT NOT NULL,
  closed_at TEXT,
  bypass INTEGER NOT NULL DEFAULT 0,
  missing_deps TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS conflicts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,
  session_code TEXT NOT NULL,
  resource_code TEXT NOT NULL,
  day TEXT NOT NULL,
  start_min INTEGER NOT NULL,
  end_min INTEGER NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS watermarks (
  key TEXT PRIMARY KEY,
  value INTEGER NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS datasets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  available INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS session_deps (
  session_code TEXT NOT NULL,
  dataset_code TEXT NOT NULL,
  PRIMARY KEY (session_code, dataset_code)
);
"""

# 老库补列：旁路标记与缺失依赖快照（全局架构 = 缺依赖旁路占用）
COLUMN_MIGRATIONS = (
    ("sessions", "bypass", "bypass INTEGER NOT NULL DEFAULT 0"),
    ("leases", "bypass", "bypass INTEGER NOT NULL DEFAULT 0"),
    ("leases", "missing_deps", "missing_deps TEXT NOT NULL DEFAULT '[]'"),
)


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def transaction():
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    for table, column, ddl in COLUMN_MIGRATIONS:
        cols = [
            r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()
        ]
        if cols and column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()
