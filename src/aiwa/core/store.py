"""Local SQLite storage: nudges, small tasks, categories, tracking choices, focus ratings."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from aiwa.core.events import Category, Finding

SCHEMA = """
CREATE TABLE IF NOT EXISTS nudges (
    id INTEGER PRIMARY KEY,
    shown_at TEXT NOT NULL,
    rule TEXT NOT NULL,
    message TEXT NOT NULL,
    response TEXT            -- e.g. 'ok', 'snooze', 'dismissed'
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    text TEXT NOT NULL,
    done_at TEXT
);
CREATE TABLE IF NOT EXISTS categories (
    key TEXT PRIMARY KEY,    -- app name, or website domain
    category TEXT NOT NULL,
    source TEXT NOT NULL,    -- 'user' or 'openjev'
    set_at TEXT NOT NULL,
    confidence REAL,         -- openjev's probability; NULL for user answers
    confirmed_at TEXT        -- when the user accepted openjev's answer; NULL if not (yet)
);
CREATE TABLE IF NOT EXISTS ratings (
    id INTEGER PRIMARY KEY,
    asked_at TEXT NOT NULL,
    answered_at TEXT NOT NULL,
    rating INTEGER,             -- 1 (scattered) .. 5 (deeply focused); NULL = skipped
    source TEXT NOT NULL,       -- 'sampled' (random popup) or 'manual' (from the tray menu)
    snapshot TEXT               -- JSON: aiwa's focus score and components at that moment
);
CREATE TABLE IF NOT EXISTS tracking (
    app_hash TEXT PRIMARY KEY,  -- sha256 of the app name
    app TEXT,                   -- the name, kept only for apps the user chose to track
    decision TEXT NOT NULL,     -- 'track' or 'never'
    set_at TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class Classification:
    category: Category
    source: str  # 'user' or 'openjev'
    confidence: float | None
    confirmed: bool = False  # the user accepted openjev's answer


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.executescript(SCHEMA)
        columns = {row[1] for row in self._db.execute("PRAGMA table_info(categories)")}
        for column, kind in [("confidence", "REAL"), ("confirmed_at", "TEXT")]:
            if column not in columns:  # databases created by older versions
                self._db.execute(f"ALTER TABLE categories ADD COLUMN {column} {kind}")

    def log_nudge(self, finding: Finding, shown_at: datetime) -> int:
        cur = self._db.execute(
            "INSERT INTO nudges (shown_at, rule, message) VALUES (?, ?, ?)",
            (shown_at.isoformat(), finding.rule, finding.message),
        )
        self._db.commit()
        return cur.lastrowid

    def set_response(self, nudge_id: int, response: str) -> None:
        self._db.execute("UPDATE nudges SET response = ? WHERE id = ?", (response, nudge_id))
        self._db.commit()

    def add_task(self, text: str, created_at: datetime) -> int:
        cur = self._db.execute(
            "INSERT INTO tasks (created_at, text) VALUES (?, ?)",
            (created_at.isoformat(), text),
        )
        self._db.commit()
        return cur.lastrowid

    def open_tasks(self) -> list[tuple[int, str]]:
        return self._db.execute(
            "SELECT id, text FROM tasks WHERE done_at IS NULL ORDER BY id"
        ).fetchall()

    def complete_task(self, task_id: int, done_at: datetime) -> None:
        self._db.execute(
            "UPDATE tasks SET done_at = ? WHERE id = ?", (done_at.isoformat(), task_id)
        )
        self._db.commit()

    def get_category(self, key: str) -> Category | None:
        row = self._db.execute("SELECT category FROM categories WHERE key = ?", (key,)).fetchone()
        return Category(row[0]) if row else None

    def get_classification(self, key: str) -> Classification | None:
        row = self._db.execute(
            "SELECT category, source, confidence, confirmed_at FROM categories WHERE key = ?", (key,)
        ).fetchone()
        return Classification(Category(row[0]), row[1], row[2], row[3] is not None) if row else None

    def confirm_category(self, key: str, confirmed_at: datetime) -> None:
        self._db.execute(
            "UPDATE categories SET confirmed_at = ? WHERE key = ?", (confirmed_at.isoformat(), key)
        )
        self._db.commit()

    def set_category(
        self,
        key: str,
        category: Category,
        source: str,
        set_at: datetime,
        confidence: float | None = None,
    ) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO categories (key, category, source, set_at, confidence)"
            " VALUES (?, ?, ?, ?, ?)",
            (key, category.value, source, set_at.isoformat(), confidence),
        )
        self._db.commit()

    def all_categories(self) -> list[tuple[str, Category, str]]:
        rows = self._db.execute("SELECT key, category, source FROM categories ORDER BY key").fetchall()
        return [(key, Category(category), source) for key, category, source in rows]

    def set_tracking(self, app: str, track: bool, set_at: datetime) -> None:
        """Remember the user's choice. For 'never', only a hash of the name is kept."""
        self._db.execute(
            "INSERT OR REPLACE INTO tracking (app_hash, app, decision, set_at) VALUES (?, ?, ?, ?)",
            (_hash(app), app if track else None, "track" if track else "never", set_at.isoformat()),
        )
        self._db.commit()

    def get_tracking(self, app: str) -> str | None:
        row = self._db.execute("SELECT decision FROM tracking WHERE app_hash = ?", (_hash(app),)).fetchone()
        return row[0] if row else None

    def tracked_apps(self) -> list[str]:
        rows = self._db.execute("SELECT app FROM tracking WHERE decision = 'track' ORDER BY app").fetchall()
        return [app for (app,) in rows]

    def add_rating(
        self, asked_at: datetime, answered_at: datetime, rating: int | None, source: str, snapshot: dict
    ) -> None:
        self._db.execute(
            "INSERT INTO ratings (asked_at, answered_at, rating, source, snapshot) VALUES (?, ?, ?, ?, ?)",
            (asked_at.isoformat(), answered_at.isoformat(), rating, source, json.dumps(snapshot)),
        )
        self._db.commit()

    def ratings(self) -> list[Rating]:
        rows = self._db.execute(
            "SELECT asked_at, answered_at, rating, source, snapshot FROM ratings ORDER BY answered_at"
        ).fetchall()
        return [
            Rating(datetime.fromisoformat(a), datetime.fromisoformat(b), r, src, json.loads(snap or "{}"))
            for a, b, r, src, snap in rows
        ]

    def forget_tracking(self, app: str) -> None:
        self._db.execute("DELETE FROM tracking WHERE app_hash = ?", (_hash(app),))
        self._db.commit()


@dataclass(frozen=True)
class Rating:
    asked_at: datetime
    answered_at: datetime
    rating: int | None  # None = skipped
    source: str
    snapshot: dict


def _hash(app: str) -> str:
    return hashlib.sha256(app.encode()).hexdigest()
