"""Signals: named quantities that change over time (focus, in a session, ...).

A `Signal` has a name and `eval(ctx)`: its value at the context's moment. It is
defined either by an `expr`, a time-series expression over the primitive series and
other signals (signals/expr.py, ops.py, primitive.py), or by a subclass that computes
`eval` in Python (the focus score). Rules (aiwa/rules) read signals by name.

`Context` is what signals are evaluated on: the moment, the recent timeline and input
counts, and the app's state values. `Values` is a read-only, lazy view of all signals
for one context: each signal is evaluated at most once (cached), only when a rule asks
for it.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime

from aiwa.core.events import InputSample, Segment

Value = float | bool | None


@dataclass
class Context:
    now: datetime
    segments: list[Segment] = field(default_factory=list)  # the recent timeline (prepared), oldest first
    latest: Segment | None = None  # what's in focus now (or away)
    state: dict[str, Value] = field(default_factory=dict)  # the app's own values (in_session, ...)
    inputs: list[InputSample] = field(default_factory=list)  # aw-watcher-input counts, oldest first
    signals: dict[str, Signal] = field(default_factory=dict, repr=False)  # by name, for expressions (set by Values)
    series: dict[str, object] = field(default_factory=dict, repr=False)  # primitive series built so far


class Signal:
    name: str
    expr: str | None = None  # e.g. "tsmean(keys, 5m)"; None when a subclass computes `eval`

    def __init__(self, name: str | None = None, expr: str | None = None):
        if name is not None:  # subclasses may set `name` on the class
            self.name = name
        self.expr = expr

    def eval(self, ctx: Context) -> Value:
        """The value at `ctx.now`; None when it can't be told."""
        if self.expr is None:
            raise NotImplementedError(f"{self.name}: no expr and no eval")
        from aiwa.signals.expr import evaluate  # expr reads signals and contexts

        return evaluate(self.expr, ctx)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.name}" + (f" = {self.expr}>" if self.expr else ">")


class Values(Mapping[str, Value]):
    """All signals' values for one context, evaluated lazily and cached."""

    def __init__(self, signals: Iterable[Signal], ctx: Context):
        self.signals = {s.name: s for s in signals}
        self.ctx = ctx
        ctx.signals.update(self.signals)
        self._cache: dict[str, Value] = {}

    def __getitem__(self, name: str) -> Value:
        if name not in self._cache:
            self._cache[name] = self.signals[name].eval(self.ctx)
        return self._cache[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self.signals)

    def __len__(self) -> int:
        return len(self.signals)
