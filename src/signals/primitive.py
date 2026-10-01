"""Primitive signals: the series recorded by the watchers, built from a context.

Everything else (focus, budgets, routines) is derived from these.

    from the timeline (window + AFK + browser watchers, prepared by core/categories.py)
        app        the app in focus                      text
        title      its window title (or the tab's)       text
        site       the domain in a browser, else the app (what gets classified)
        category   "deep", "shallow", "distraction", "neutral"; unknown while away
        away       true while away (AFK, screen locked)
        active     the opposite: true while at the computer

    from aw-watcher-input (per minute; unknown without the watcher)
        keys       key presses
        clicks     mouse clicks
        moved      mouse movement, in pixels
        scrolled   scrolling

The app's own state (in_session, ...) is not a series yet: it is only known now, and
expressions read it as a number (see signals/expr.py).
"""

from __future__ import annotations

from collections.abc import Callable

from aiwa.core.events import Segment
from aiwa.signals.base import Context
from aiwa.signals.series import Piece, Piecewise, Series


def _timeline(value: Callable[[Segment], object]) -> Callable[[Context], Series]:
    def build(ctx: Context) -> Series:
        return Piecewise(Piece(s.start, s.end, value(s)) for s in ctx.segments)

    return build


def _inputs(field: str) -> Callable[[Context], Series]:
    def build(ctx: Context) -> Series:
        pieces = []
        for sample in ctx.inputs:
            minutes = (sample.end - sample.start).total_seconds() / 60
            if minutes > 0:
                pieces.append(Piece(sample.start, sample.end, getattr(sample, field) / minutes))
        return Piecewise(pieces)

    return build


PRIMITIVES: dict[str, Callable[[Context], Series]] = {
    "app": _timeline(lambda s: None if s.away else s.app),
    "title": _timeline(lambda s: None if s.away else s.title),
    "site": _timeline(lambda s: None if s.away else s.key),
    "category": _timeline(lambda s: None if s.away or s.category is None else s.category.value),
    "away": _timeline(lambda s: s.away),
    "active": _timeline(lambda s: not s.away),
    "keys": _inputs("keys"),
    "clicks": _inputs("clicks"),
    "moved": _inputs("moved"),
    "scrolled": _inputs("scrolled"),
}


def primitive(name: str, ctx: Context) -> Series:
    """The primitive series `name`, built once per context."""
    if name not in ctx.series:
        ctx.series[name] = PRIMITIVES[name](ctx)
    return ctx.series[name]
