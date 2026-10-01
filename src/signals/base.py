"""Signals: named quantities that change over time (focus, in a session, ...).

A `Signal` has a name and `eval(ctx)`: its value at the context's moment. Subclasses
define what to compute; rules (aiwa/rules) read signals by name.

`Context` is what signals are evaluated on: the moment, the recent timeline, and the
app's state values. `Values` is a read-only, lazy view of all signals for one context:
each signal is evaluated at most once (cached), only when a rule asks for it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime

from aiwa.core.events import Segment

Value = float | bool | None


@dataclass
class Context:
    now: datetime
    segments: list[Segment] = field(default_factory=list)  # the recent timeline (prepared), oldest first
    latest: Segment | None = None  # what's in focus now (or away)
    state: dict[str, Value] = field(default_factory=dict)  # the app's own values (in_session, ...)


class Signal(ABC):
    name: str

    @abstractmethod
    def eval(self, ctx: Context) -> Value:
        """The value at `ctx.now`; None when it can't be told."""

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.name}>"


class Values(Mapping[str, Value]):
    """All signals' values for one context, evaluated lazily and cached."""

    def __init__(self, signals: Iterable[Signal], ctx: Context):
        self.signals = {s.name: s for s in signals}
        self.ctx = ctx
        self._cache: dict[str, Value] = {}

    def __getitem__(self, name: str) -> Value:
        if name not in self._cache:
            self._cache[name] = self.signals[name].eval(self.ctx)
        return self._cache[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self.signals)

    def __len__(self) -> int:
        return len(self.signals)
