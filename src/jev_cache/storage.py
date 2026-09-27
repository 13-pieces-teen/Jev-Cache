"""SQLite is owned by the background runtime, never by the GUI thread."""

from __future__ import annotations

import base64
import json
import os
import sqlite3
import time
from pathlib import Path


def data_directory() -> Path:
    result = Path(os.getenv("JEVCACHE_DATA_DIR") or Path(os.getenv("LOCALAPPDATA", Path.home())) / "JevCache")
    result.mkdir(parents=True, exist_ok=True)
    return result


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA cache_size=-1024")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS memory (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS actions (id TEXT PRIMARY KEY, at REAL NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS decisions (id TEXT PRIMARY KEY, at REAL NOT NULL, body TEXT NOT NULL);
        """)
        self.db.commit()

    def get(self, key: str, default=None):
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, key: str, value):
        self.db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, json.dumps(value)))
        self.db.commit()

    def memories(self) -> dict:
        return {key: json.loads(value) for key, value in self.db.execute("SELECT key,value FROM memory")}

    def remember(self, key: str, value):
        self.db.execute("INSERT OR REPLACE INTO memory VALUES (?,?,?)", (key, json.dumps(value), time.time()))
        self.db.commit()

    def forget(self):
        self.db.execute("DELETE FROM memory")
        # Decisions and action snapshots may contain learned context; don't reconstruct deleted memory.
        self.db.execute("DELETE FROM decisions")
        self.db.execute("DELETE FROM actions")
        self.put("memory_version", self.get("memory_version", 0) + 1)
        self.db.commit()
        self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def receipt(self, action_id: str, body: dict):
        self.db.execute(
            "INSERT OR REPLACE INTO actions VALUES (?,?,?)",
            (action_id, body.get("at", time.time()), json.dumps(body, ensure_ascii=False)),
        )
        self.db.commit()

    def decision(self, run_id: str, body: dict):
        self.db.execute(
            "INSERT OR REPLACE INTO decisions VALUES (?,?,?)",
            (run_id, time.time(), json.dumps(body, ensure_ascii=False)),
        )
        self.db.commit()

    def recent(self, limit=30) -> list[dict]:
        return [
            json.loads(row[0])
            for row in self.db.execute("SELECT body FROM actions ORDER BY at DESC LIMIT ?", (limit,))
        ]

    def prune(self):
        cutoff = time.time() - 7 * 86400
        for table in ("actions", "decisions"):
            self.db.execute(f"DELETE FROM {table} WHERE at < ?", (cutoff,))
        self.db.execute("DELETE FROM memory WHERE updated < ?", (time.time() - 30 * 86400,))
        for table in ("actions", "decisions"):
            self.db.execute(
                f"DELETE FROM {table} WHERE id NOT IN (SELECT id FROM {table} ORDER BY at DESC LIMIT 1000)"
            )
        self.db.commit()
        self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def close(self):
        self.db.close()


def protect_secret(secret: str) -> str:
    import win32crypt

    return base64.b64encode(
        win32crypt.CryptProtectData(secret.encode(), "JevCache", None, None, None, 0)
    ).decode()


def unprotect_secret(encrypted: str) -> str:
    if not encrypted:
        return ""
    try:
        import win32crypt

        return win32crypt.CryptUnprotectData(base64.b64decode(encrypted), None, None, None, 0)[1].decode()
    except Exception:
        return ""
