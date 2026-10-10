"""SQLite credit ledger for hosted MCP keys."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class Ledger:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS keys (
              id INTEGER PRIMARY KEY,
              key_hash TEXT UNIQUE NOT NULL,
              label TEXT NOT NULL,
              credits INTEGER NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS usage (
              id INTEGER PRIMARY KEY,
              key_id INTEGER NOT NULL,
              tool TEXT NOT NULL,
              credits INTEGER NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS trials (
              ip TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            """
        )
        self._db.commit()

    def create_key(self, label: str, credits: int) -> str:
        raw = "sm_" + secrets.token_urlsafe(24)
        with self._lock:
            self._db.execute(
                "INSERT INTO keys (key_hash, label, credits, created_at) VALUES (?, ?, ?, ?)",
                (hash_key(raw), label, credits, _now()),
            )
            self._db.commit()
        return raw

    def lookup(self, raw: str) -> sqlite3.Row | None:
        with self._lock:
            return self._db.execute(
                "SELECT id, label, credits FROM keys WHERE key_hash = ?",
                (hash_key(raw),),
            ).fetchone()

    def balance(self, key_id: int) -> int:
        with self._lock:
            row = self._db.execute(
                "SELECT credits FROM keys WHERE id = ?", (key_id,)
            ).fetchone()
        return int(row["credits"]) if row else 0

    def debit(self, key_id: int, tool: str, credits: int) -> bool:
        """Spend credits. A zero charge still records the call and succeeds."""
        if credits < 0:
            raise ValueError("credits")
        with self._lock:
            if credits == 0:
                self._db.execute(
                    "INSERT INTO usage (key_id, tool, credits, created_at) VALUES (?, ?, 0, ?)",
                    (key_id, tool, _now()),
                )
                self._db.commit()
                return True
            cur = self._db.execute(
                "UPDATE keys SET credits = credits - ? WHERE id = ? AND credits >= ?",
                (credits, key_id, credits),
            )
            if cur.rowcount != 1:
                self._db.rollback()
                return False
            self._db.execute(
                "INSERT INTO usage (key_id, tool, credits, created_at) VALUES (?, ?, ?, ?)",
                (key_id, tool, credits, _now()),
            )
            self._db.commit()
            return True

    def credit(self, key_id: int, amount: int, tool: str = "refund") -> None:
        if amount < 0:
            raise ValueError("amount")
        with self._lock:
            self._db.execute(
                "UPDATE keys SET credits = credits + ? WHERE id = ?",
                (amount, key_id),
            )
            self._db.execute(
                "INSERT INTO usage (key_id, tool, credits, created_at) VALUES (?, ?, ?, ?)",
                (key_id, tool, -amount, _now()),
            )
            self._db.commit()

    def trial_allowed(self, ip: str, limit: int = 3, hours: int = 24) -> bool:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        with self._lock:
            row = self._db.execute(
                "SELECT COUNT(*) AS n FROM trials WHERE ip = ? AND created_at >= ?",
                (ip, cutoff),
            ).fetchone()
            return int(row["n"]) < limit

    def record_trial(self, ip: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO trials (ip, created_at) VALUES (?, ?)",
                (ip, _now()),
            )
            self._db.commit()

    def hit_allowed(self, ip: str, kind: str, limit: int, hours: int = 1) -> bool:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        with self._lock:
            self._db.execute(
                """
                CREATE TABLE IF NOT EXISTS portal_hits (
                  ip TEXT NOT NULL,
                  kind TEXT NOT NULL,
                  created_at TEXT NOT NULL
                )
                """
            )
            row = self._db.execute(
                "SELECT COUNT(*) AS n FROM portal_hits WHERE ip = ? AND kind = ? AND created_at >= ?",
                (ip, kind, cutoff),
            ).fetchone()
            return int(row["n"]) < limit

    def record_hit(self, ip: str, kind: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO portal_hits (ip, kind, created_at) VALUES (?, ?, ?)",
                (ip, kind, _now()),
            )
            self._db.commit()
