"""Signals from the app's own state and the latest segment."""

from __future__ import annotations

from aiwa.core.events import Category
from aiwa.signals.base import Context, Signal, Value


class State(Signal):
    """A value the app puts into the context (in_session, shutdown_done, popup_open, ...)."""

    def __init__(self, name: str):
        self.name = name

    def eval(self, ctx: Context) -> Value:
        return ctx.state.get(self.name)


class OnCategory(Signal):
    """Whether what's in focus now counts as `category` (False when away)."""

    def __init__(self, name: str, category: Category):
        self.name, self.category = name, category

    def eval(self, ctx: Context) -> Value:
        return ctx.latest is not None and not ctx.latest.away and ctx.latest.category is self.category
