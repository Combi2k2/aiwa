"""Time-series operators, on the sparse series of signals/series.py.

Our own functions, not Polars: the data is a few hours of intervals, and these work
on intervals exactly (a window sum over a piecewise series is exact, no resampling).

Pointwise (a value at each moment):
    lift(f, x, y, ...)   f applied at each moment; numbers count as constant series
    delay(x, d)          x as it was `d` ago

Over a trailing window [t − w, t], at each moment t:
    tssum(x, w)     ∫ x dt, time in minutes: a rate gives a count, true / false gives minutes
    tsmean(x, w)    time-weighted mean over the known part of the window
    tsmax(x, w), tsmin(x, w)
    tscount(x, w)   how many pieces begin in the window: changes (switches), or entries
                    when `x` is true / false (only the true pieces are counted)

Each returns a series, so they nest: `delay(tsmean(keys, 5m), 2m)`. Pointwise ops on
`Piecewise` series stay piecewise and exact; anything else is `Lazy`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from aiwa.signals.series import Lazy, Piece, Piecewise, Series, constant

Operand = Series | float | int | bool | str | None


def _series(x: Operand) -> Series:
    return x if isinstance(x, Series) else constant(x)


def lift(f: Callable[..., Any], *xs: Operand) -> Series:
    """`f` of the operands' values at each moment; None (unknown) when any of them is."""

    def apply(*values):
        return None if any(v is None for v in values) else f(*values)

    series = [x for x in xs if isinstance(x, Series)]
    if series and all(isinstance(x, Piecewise) for x in series):
        cuts = sorted({t for x in series for p in x for t in (p.start, p.end)})
        pieces = []
        for start, end in zip(cuts, cuts[1:]):
            values = [x.at(end) if isinstance(x, Series) else x for x in xs]
            pieces.append(Piece(start, end, apply(*values)))
        return Piecewise(pieces)
    operands = [_series(x) for x in xs]
    return Lazy(lambda t: apply(*(x.at(t) for x in operands)))


def delay(x: Operand, d: timedelta) -> Series:
    if isinstance(x, Piecewise):
        return Piecewise(Piece(p.start + d, p.end + d, p.value) for p in x)
    x = _series(x)
    return Lazy(lambda t: x.at(t - d))


def _minutes(p: Piece) -> float:
    return (p.end - p.start).total_seconds() / 60


def _window(x: Operand, w: timedelta, reduce: Callable[[list[Piece]], Any]) -> Series:
    x = _series(x)
    return Lazy(lambda t: reduce(x.pieces(t - w, t)))


def _sum(pieces: list[Piece]) -> float:
    return sum(float(p.value) * _minutes(p) for p in pieces)


def _mean(pieces: list[Piece]) -> float | None:
    known = sum(_minutes(p) for p in pieces)
    return _sum(pieces) / known if known else None


def tssum(x: Operand, w: timedelta) -> Series:
    return _window(x, w, _sum)


def tsmean(x: Operand, w: timedelta) -> Series:
    return _window(x, w, _mean)


def tsmax(x: Operand, w: timedelta) -> Series:
    return _window(x, w, lambda ps: max((p.value for p in ps), default=None))


def tsmin(x: Operand, w: timedelta) -> Series:
    return _window(x, w, lambda ps: min((p.value for p in ps), default=None))


def tscount(x: Operand, w: timedelta) -> Series:
    x = _series(x)

    def count(t: datetime) -> int:
        begun = [p for p in x.pieces(t - w, t) if p.start > t - w]  # not the one already running
        return sum(1 for p in begun if p.value is not False)

    return Lazy(count)


# the functions an expression can call (signals/expr.py)
FUNCTIONS: dict[str, Callable[..., Series]] = {
    "delay": delay,
    "tssum": tssum,
    "tsmean": tsmean,
    "tsmax": tsmax,
    "tsmin": tsmin,
    "tscount": tscount,
}
