"""Turns raw ActivityWatch data into one ordered list of segments."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from aiwa.core.events import Segment

BROWSER_APPS = {
    "Microsoft Edge",
    "Google Chrome",
    "Brave Browser",
    "Chromium",
    "Firefox",
    "Vivaldi",
    "Safari",
    "Opera",
    "Arc",
}


@dataclass(frozen=True)
class Tab:
    """The active browser tab, from the ActivityWatch web extension."""

    start: datetime
    end: datetime
    url: str
    title: str


Interval = tuple[datetime, datetime]


def build(windows: list[Segment], away: list[Interval], tabs: list[Tab]) -> list[Segment]:
    """Remove away time from window segments, attach browser tabs, add away segments."""
    segments = []
    for window in windows:
        for start, end in _subtract(window.start, window.end, away):
            piece = replace(window, start=start, end=end)
            if window.app in BROWSER_APPS:
                tab = _best_overlap(tabs, start, end)
                if tab:
                    piece = replace(piece, url=tab.url, title=tab.title or piece.title)
            segments.append(piece)
    segments += [Segment(start, end, "(away)", away=True) for start, end in away]
    return sorted(segments, key=lambda s: s.start)


def _subtract(start: datetime, end: datetime, intervals: list[Interval]) -> list[Interval]:
    pieces = [(start, end)]
    for cut_start, cut_end in intervals:
        remaining = []
        for s, e in pieces:
            if cut_end <= s or cut_start >= e:
                remaining.append((s, e))
                continue
            if s < cut_start:
                remaining.append((s, cut_start))
            if cut_end < e:
                remaining.append((cut_end, e))
        pieces = remaining
    return [(s, e) for s, e in pieces if e > s]


def _best_overlap(tabs: list[Tab], start: datetime, end: datetime) -> Tab | None:
    best, best_overlap = None, 0.0
    for tab in tabs:
        overlap = (min(end, tab.end) - max(start, tab.start)).total_seconds()
        if overlap > best_overlap:
            best, best_overlap = tab, overlap
    return best


def merge(segments: list[Segment], max_gap: timedelta = timedelta(seconds=5)) -> list[Segment]:
    """Join back-to-back segments that look the same (e.g. a title that keeps
    changing inside an untracked app), allowing small gaps between them."""
    merged: list[Segment] = []
    for segment in segments:
        last = merged[-1] if merged else None
        if (
            last
            and (last.app, last.title, last.url, last.category, last.away)
            == (segment.app, segment.title, segment.url, segment.category, segment.away)
            and segment.start - last.end <= max_gap
        ):
            merged[-1] = replace(last, end=max(last.end, segment.end))
        else:
            merged.append(segment)
    return merged
