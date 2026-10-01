from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from urllib.parse import urlsplit


class Category(Enum):
    """What kind of work an activity is, in Deep Work terms."""

    DEEP = "deep"  # cognitively demanding, creates value, hard to replicate
    SHALLOW = "shallow"  # logistics and communication, easy to replicate
    DISTRACTION = "distraction"  # entertainment unrelated to work
    NEUTRAL = "neutral"  # system tools that are neither


@dataclass(frozen=True)
class InputSample:
    """What aw-watcher-input counted over [start, end) (one event, about 5 seconds)."""

    start: datetime
    end: datetime
    keys: float = 0  # key presses (aw-watcher-input counts down and up: its `presses` / 2)
    clicks: float = 0
    moved: float = 0  # mouse movement, in pixels
    scrolled: float = 0  # scrolling, in scroll units

    @classmethod
    def from_event(cls, start: datetime, end: datetime, data: dict) -> InputSample:
        moved = abs(data.get("deltaX", 0)) + abs(data.get("deltaY", 0))
        scrolled = abs(data.get("scrollX", 0)) + abs(data.get("scrollY", 0))
        return cls(start, end, data.get("presses", 0) / 2, data.get("clicks", 0), moved, scrolled)


@dataclass(frozen=True)
class Segment:
    """A stretch of time with one thing in focus, or with the user away."""

    start: datetime
    end: datetime
    app: str
    title: str = ""
    url: str | None = None
    category: Category | None = None  # None = not classified yet
    away: bool = False
    inputs: float | None = None  # input actions per minute (keys + clicks); None = no input data

    @property
    def duration(self) -> timedelta:
        return self.end - self.start

    @property
    def key(self) -> str:
        """What gets classified: the website's domain in a browser, otherwise the app.

        The same site counts the same in any browser, and every page on it
        shares one answer.
        """
        if self.url:
            parts = urlsplit(self.url)
            if parts.scheme in ("http", "https") and parts.hostname:
                return parts.hostname.removeprefix("www.")
            return f"{self.app} · {parts.scheme or 'page'}"  # browser-internal page
        return self.app


class Level(Enum):
    """How strongly to interrupt the user."""

    QUIET = "quiet"  # tray badge only
    NOTIFY = "notify"  # system notification
    POPUP = "popup"  # floating panel asking for a response


@dataclass(frozen=True)
class Finding:
    """Something a rule noticed that may be worth telling the user."""

    rule: str
    message: str
    level: Level = Level.NOTIFY
