"""Classifies segments as deep, shallow, distraction or neutral."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import timedelta

from aiwa.config import UNTRACKED, CategoryRule, Config
from aiwa.core.events import Category, Segment
from aiwa.core.store import Store
from aiwa.core.timeline import BROWSER_APPS, merge


class Categorizer:
    """Config rules first, then what the user answered before."""

    def __init__(self, rules: list[CategoryRule], store: Store):
        self.rules = rules
        self.store = store

    def categorize(self, segment: Segment) -> Category | None:
        if segment.url and not segment.url.startswith(("http://", "https://")):
            return Category.NEUTRAL  # browser-internal pages: new tab, settings, extensions
        for rule in self.rules:
            if rule.match.matches(segment.app, segment.title, segment.url):
                return rule.category
        return self.store.get_category(segment.key)


def prepare(segments: list[Segment], config: Config, categorizer: Categorizer) -> list[Segment]:
    """Categorize every segment, then hide the names of untracked ones.

    Untracked activity keeps its category (so a distraction still counts as
    one) but loses its app name, title and URL.
    """
    prepared = []
    for segment in segments:
        if segment.away:
            prepared.append(segment)
            continue
        category = categorizer.categorize(segment)
        if config.is_tracked(segment.app, segment.title, segment.url):
            prepared.append(replace(segment, category=category))
        else:
            prepared.append(replace(segment, app=UNTRACKED, title="", url=None, category=category))
    return merge(prepared)


def unknown(segments: list[Segment], min_time: timedelta) -> list[tuple[str, timedelta]]:
    """Unclassified tracked activities used at least `min_time`, most used first.

    Browsers are only asked about per website: a browser segment without a
    URL (no ActivityWatch web extension) is never offered, because "the whole
    browser" is both work and distraction.
    """
    totals: Counter[str] = Counter()
    for segment in segments:
        if segment.away or segment.category is not None or segment.app == UNTRACKED:
            continue
        if segment.app in BROWSER_APPS and not segment.url:
            continue
        totals[segment.key] += segment.duration.total_seconds()
    return [
        (key, timedelta(seconds=seconds))
        for key, seconds in totals.most_common()
        if seconds >= min_time.total_seconds()
    ]


def label(segment: Segment) -> str:
    """Short category label for display."""
    if segment.away:
        return "away"
    if segment.category:
        return segment.category.value
    return "untracked" if segment.app == UNTRACKED else "unclassified"


def summary(segments: list[Segment], minutes: int) -> str:
    """Tray status line, e.g. "last 30 min: 18m deep · 6m shallow · 2m unclassified"."""
    totals: dict[str, float] = {}
    for s in segments:
        if not s.away:
            name = label(s)
            totals[name] = totals.get(name, 0) + s.duration.total_seconds()
    parts = [
        f"{round(sec / 60)}m {name}" if sec >= 60 else f"{round(sec)}s {name}"
        for name, sec in sorted(totals.items(), key=lambda x: -x[1])
    ]
    return f"last {minutes} min: " + (" · ".join(parts) or "no activity")
