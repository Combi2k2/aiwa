"""Classifies segments as deep, shallow, distraction or neutral."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import timedelta

from aiwa import platforms
from aiwa.config import UNTRACKED, CategoryRule, Config
from aiwa.core.events import Category, Segment
from aiwa.core.store import Store
from aiwa.core.interpret import tools_take_context, watching_is_not_away
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

    def kind(self, segment: Segment) -> str | None:
        known = self.store.get_kind(segment.key)
        return known[0] if known else None


def prepare(segments: list[Segment], config: Config, categorizer: Categorizer) -> list[Segment]:
    """Categorize every segment, apply what the kinds mean (core/interpret.py:
    watching is not away, tools take their context), then hide the names of
    untracked ones.

    Untracked activity keeps its category (so a distraction still counts as
    one) but loses its app name, title and URL.
    """
    lock_apps = platforms.current().LOCK_APPS
    segments = [replace(s, away=True) if s.app in lock_apps else s for s in segments]  # a locked screen is away
    categorized = [s if s.away else replace(s, category=categorizer.categorize(s)) for s in segments]
    kinds: dict[str, str | None] = {}

    def kind_of(segment: Segment) -> str | None:
        if not config.is_tracked(segment.app, segment.title, segment.url):
            return None  # untracked: nothing is known about it
        if segment.key not in kinds:
            kinds[segment.key] = categorizer.kind(segment)
        return kinds[segment.key]

    interpreted = tools_take_context(watching_is_not_away(categorized, kind_of), kind_of)
    prepared = []
    for segment in interpreted:
        if segment.away or config.is_tracked(segment.app, segment.title, segment.url):
            prepared.append(segment)
        else:
            prepared.append(replace(segment, app=UNTRACKED, title="", url=None))
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
