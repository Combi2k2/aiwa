"""Time series: a value over time, the way ActivityWatch records it.

ActivityWatch stores events as (timestamp, duration, data) and merges identical
neighbours (heartbeats), so its data is sparse and piecewise constant: a value holds
over an interval, and there are gaps where nothing is known. `Piecewise` keeps exactly
that: sorted pieces (start, end, value), equal neighbours merged, gaps left out.

A value at time t is the value of the piece with start < t <= end: what held just
before t, so a series built from segments ending now has a value at now.

Counts are kept as rates per minute (key presses / min), so summing a series over a
window (`ops.tssum`) gives a count for a rate and minutes for a true / false series.

Derived series that aren't piecewise constant (a moving mean, the focus score) are
`Lazy`: they compute `at(t)` on demand, and give pieces by sampling every `STEP`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from bisect import bisect_left
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from typing import Any, NamedTuple

STEP = timedelta(seconds=10)  # sampling step for lazy series


class Piece(NamedTuple):
    start: datetime
    end: datetime
    value: Any


class Series(ABC):
    @abstractmethod
    def at(self, t: datetime) -> Any:
        """The value just before `t`; None where unknown."""

    @abstractmethod
    def pieces(self, start: datetime, end: datetime) -> list[Piece]:
        """The pieces between `start` and `end`, clipped to them."""


class Piecewise(Series):
    def __init__(self, pieces: Iterable[Piece | tuple] = ()):
        merged: list[Piece] = []
        for start, end, value in sorted(pieces, key=lambda p: p[0]):
            if merged:
                start = max(start, merged[-1].end)  # overlaps: the earlier piece wins
            if value is None or end <= start:
                continue
            last = merged[-1] if merged else None
            if last is not None and last.end == start and last.value == value:
                merged[-1] = Piece(last.start, end, value)
            else:
                merged.append(Piece(start, end, value))
        self._pieces = merged
        self._ends = [p.end for p in merged]

    def at(self, t: datetime) -> Any:
        i = bisect_left(self._ends, t)  # the first piece ending at or after t
        if i < len(self._pieces) and self._pieces[i].start < t:
            return self._pieces[i].value
        return None

    def pieces(self, start: datetime, end: datetime) -> list[Piece]:
        result = []
        for p in self._pieces[bisect_left(self._ends, start):]:
            if p.start >= end:
                break
            s, e = max(p.start, start), min(p.end, end)
            if e > s:
                result.append(Piece(s, e, p.value))
        return result

    @property
    def span(self) -> tuple[datetime, datetime] | None:
        return (self._pieces[0].start, self._pieces[-1].end) if self._pieces else None

    def __iter__(self):
        return iter(self._pieces)

    def __len__(self) -> int:
        return len(self._pieces)

    def __repr__(self) -> str:
        return f"Piecewise({self._pieces!r})"


class Lazy(Series):
    """A series known only by its value at each moment."""

    def __init__(self, at: Callable[[datetime], Any], step: timedelta = STEP):
        self._at, self.step = at, step

    def at(self, t: datetime) -> Any:
        return self._at(t)

    def pieces(self, start: datetime, end: datetime) -> list[Piece]:
        """Sampled: each step holds the value at its end."""
        samples, t = [], end
        while t > start:
            samples.append(Piece(max(t - self.step, start), t, self._at(t)))
            t -= self.step
        return list(Piecewise(samples))


def constant(value: Any) -> Series:
    return Lazy(lambda t: value)
