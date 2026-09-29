"""Local SQLite storage: nudges, small tasks, categories, tracking choices, focus ratings, focus minutes."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
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
CREATE TABLE IF NOT EXISTS focus_minutes (
    minute TEXT PRIMARY KEY,    -- start of the minute, UTC
    intensity REAL,             -- main-window focus intensity at its end; NULL = mostly away
    activity TEXT               -- what was mostly done: deep, shallow, ..., away; NULL = no data
);
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT,              -- NULL while the session is running
    pokes INTEGER DEFAULT 0,
    asked_done INTEGER DEFAULT 0,
    wrap_ups INTEGER DEFAULT 0,
    alarms INTEGER DEFAULT 0,
    ended_by TEXT               -- 'user', or 'away' (ended itself after 10 min away)
);
CREATE TABLE IF NOT EXISTS plans (
    day TEXT PRIMARY KEY,       -- the day being planned (YYYY-MM-DD, aiwa's day)
    block_start TEXT NOT NULL,  -- HH:MM: this day's block starts at a different time
    made_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS block_log (
    day TEXT NOT NULL,
    action TEXT NOT NULL,       -- 'skipped'
    at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS todos (
    id INTEGER PRIMARY KEY,
    day TEXT NOT NULL,          -- the day it was planned for; open ones carry over
    text TEXT NOT NULL,
    kind TEXT,                  -- 'deep' or 'shallow' (openjev's estimate)
    minutes INTEGER,            -- estimated size (openjev); NULL = unknown
    position INTEGER NOT NULL,  -- order within the day
    status TEXT NOT NULL DEFAULT 'open',  -- 'open', 'done' or 'dropped'
    created_at TEXT NOT NULL,
    done_at TEXT
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
        if "ended_by" not in {row[1] for row in self._db.execute("PRAGMA table_info(sessions)")}:
            self._db.execute("ALTER TABLE sessions ADD COLUMN ended_by TEXT")

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

    def save_minutes(self, entries: list) -> None:
        self._db.executemany(
            "INSERT OR REPLACE INTO focus_minutes (minute, intensity, activity) VALUES (?, ?, ?)",
            [(e.minute.isoformat(), e.intensity, e.activity) for e in entries],
        )
        self._db.commit()

    def minutes(self, start: datetime, end: datetime) -> list:
        from aiwa.core.scoreboard.ledger import MinuteEntry

        rows = self._db.execute(
            "SELECT minute, intensity, activity FROM focus_minutes WHERE minute >= ? AND minute < ? ORDER BY minute",
            (start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat()),
        ).fetchall()
        return [MinuteEntry(datetime.fromisoformat(m), i, a) for m, i, a in rows]

    def last_minute(self) -> datetime | None:
        row = self._db.execute("SELECT MAX(minute) FROM focus_minutes").fetchone()
        return datetime.fromisoformat(row[0]) if row and row[0] else None

    def start_session(self, started_at: datetime) -> int:
        cur = self._db.execute("INSERT INTO sessions (started_at) VALUES (?)", (started_at.isoformat(),))
        self._db.commit()
        return cur.lastrowid

    def running_session(self) -> tuple[int, datetime] | None:
        row = self._db.execute(
            "SELECT id, started_at FROM sessions WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return (row[0], datetime.fromisoformat(row[1])) if row else None

    def end_session(self, session_id: int, ended_at: datetime, counts: dict[str, int], ended_by: str) -> None:
        self._db.execute(
            "UPDATE sessions SET ended_at = ?, pokes = ?, asked_done = ?, wrap_ups = ?, alarms = ?, ended_by = ?"
            " WHERE id = ?",
            (ended_at.isoformat(), counts.get("poke", 0), counts.get("ask_done", 0),
             counts.get("wrap_up", 0), counts.get("alarm", 0), ended_by, session_id),
        )
        self._db.commit()

    def save_plan(self, day: date, block_start: time, made_at: datetime) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO plans (day, block_start, made_at) VALUES (?, ?, ?)",
            (day.isoformat(), block_start.strftime("%H:%M"), made_at.isoformat()),
        )
        self._db.commit()

    def get_plan(self, day: date):
        from aiwa.core.schedule import Plan

        row = self._db.execute("SELECT block_start FROM plans WHERE day = ?", (day.isoformat(),)).fetchone()
        return Plan(day, time.fromisoformat(row[0])) if row else None

    def todos_planned_for(self, day: date) -> int:
        (n,) = self._db.execute("SELECT COUNT(*) FROM todos WHERE day = ?", (day.isoformat(),)).fetchone()
        return n

    def log_block(self, day: date, action: str, at: datetime) -> None:
        self._db.execute("INSERT INTO block_log (day, action, at) VALUES (?, ?, ?)", (day.isoformat(), action, at.isoformat()))
        self._db.commit()

    def block_actions(self, day: date) -> set[str]:
        return {a for (a,) in self._db.execute("SELECT action FROM block_log WHERE day = ?", (day.isoformat(),))}

    def sessions_between(self, start: datetime, end: datetime) -> list[tuple]:
        """(started_at, ended_at or None, pokes, ended_by) for sessions started in [start, end)."""
        rows = self._db.execute(
            "SELECT started_at, ended_at, pokes, ended_by FROM sessions WHERE started_at >= ? AND started_at < ?"
            " ORDER BY started_at",
            (start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat()),
        ).fetchall()
        return [
            (datetime.fromisoformat(a), datetime.fromisoformat(b) if b else None, pokes or 0, by)
            for a, b, pokes, by in rows
        ]

    def add_todos(self, day: date, items: list[tuple[str, str | None, int | None]], now: datetime) -> None:
        """Append (text, kind, minutes) items to the day's list, in order."""
        (last,) = self._db.execute("SELECT COALESCE(MAX(position), 0) FROM todos WHERE day = ?", (day.isoformat(),)).fetchone()
        self._db.executemany(
            "INSERT INTO todos (day, text, kind, minutes, position, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            [(day.isoformat(), text, kind, minutes, last + i, now.isoformat()) for i, (text, kind, minutes) in enumerate(items, 1)],
        )
        self._db.commit()

    def open_todos(self, until: date) -> list[Todo]:
        """Open tasks planned for `until` or earlier (unfinished ones carry over), in order."""
        rows = self._db.execute(
            "SELECT id, day, text, kind, minutes, status FROM todos WHERE status = 'open' AND day <= ?"
            " ORDER BY day, position",
            (until.isoformat(),),
        ).fetchall()
        return [Todo(i, date.fromisoformat(d), t, k, m, st) for i, d, t, k, m, st in rows]

    def todos_done_between(self, start: datetime, end: datetime) -> int:
        (n,) = self._db.execute(
            "SELECT COUNT(*) FROM todos WHERE status = 'done' AND done_at >= ? AND done_at < ?",
            (start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat()),
        ).fetchone()
        return n

    def set_todo_status(self, todo_id: int, status: str, at: datetime) -> None:
        self._db.execute(
            "UPDATE todos SET status = ?, done_at = ? WHERE id = ?",
            (status, at.astimezone(timezone.utc).isoformat() if status != "open" else None, todo_id),
        )
        self._db.commit()

    def move_todo_to_end(self, todo_id: int, day: date) -> None:
        """Put a task after everything else for `day` ("pick another one first")."""
        (last,) = self._db.execute("SELECT COALESCE(MAX(position), 0) FROM todos WHERE day = ?", (day.isoformat(),)).fetchone()
        self._db.execute("UPDATE todos SET day = ?, position = ? WHERE id = ?", (day.isoformat(), last + 1, todo_id))
        self._db.commit()

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


@dataclass(frozen=True)
class Todo:
    id: int
    day: date
    text: str
    kind: str | None
    minutes: int | None
    status: str


def _hash(app: str) -> str:
    return hashlib.sha256(app.encode()).hexdigest()
