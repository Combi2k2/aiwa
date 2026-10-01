from datetime import datetime, timedelta, timezone

import pytest

from aiwa.core.events import Category, InputSample, Segment
from aiwa.signals.base import Context, Signal, Values
from aiwa.signals.defaults import default_signals
from aiwa.signals.expr import ExprError
from aiwa.signals.focus.params import FocusParams
from aiwa.signals.ops import delay, lift, tscount, tsmax, tsmean, tssum
from aiwa.signals.series import Piecewise

T0 = datetime(2026, 10, 1, 10, tzinfo=timezone.utc)
MIN = timedelta(minutes=1)


def at(minutes):
    return T0 + timedelta(minutes=minutes)


def series(*pieces):
    return Piecewise((at(a), at(b), v) for a, b, v in pieces)


def test_piecewise_holds_values_merges_and_keeps_gaps():
    s = series((0, 2, 1), (2, 4, 1), (5, 6, 3))
    assert len(s) == 2  # the equal neighbours merged
    assert (s.at(at(0)), s.at(at(1)), s.at(at(4)), s.at(at(4.5)), s.at(at(6)), s.at(at(7))) == (None, 1, 1, None, 3, None)


def test_lift_is_exact_on_piecewise():
    x, y = series((0, 4, 1)), series((2, 6, 10))
    total = lift(lambda a, b: a + b, x, y)
    assert isinstance(total, Piecewise) and [(p.value) for p in total] == [11]  # only where both are known
    assert lift(lambda a, b: a * b, x, 3).at(at(1)) == 3


def test_delay_shifts():
    assert delay(series((0, 1, 5)), 2 * MIN).at(at(2.5)) == 5


def test_window_operators():
    keys = series((0, 2, 30), (2, 4, 60), (5, 6, 0))  # presses per minute; unknown in (4, 5]
    assert tssum(keys, 10 * MIN).at(at(6)) == 30 * 2 + 60 * 2
    assert tsmean(keys, 10 * MIN).at(at(6)) == pytest.approx(180 / 5)  # over the known 5 minutes
    assert tsmax(keys, 3 * MIN).at(at(6)) == 60
    assert tsmean(keys, MIN).at(at(20)) is None


def test_tscount_counts_entries():
    on = series((0, 1, True), (1, 2, False), (2, 3, True), (3, 9, False))
    assert tscount(on, 10 * MIN).at(at(9)) == 2
    assert tscount(on, 7.5 * MIN).at(at(9)) == 1  # the first entry is before the window


def test_nesting_lazy_series():
    keys = series((0, 5, 10), (5, 10, 40))
    rise = lift(lambda a, b: a - b, tsmean(keys, 2 * MIN), delay(tsmean(keys, 2 * MIN), 5 * MIN))
    assert rise.at(at(10)) == pytest.approx(30)


SEGMENTS = [Segment(at(0), at(3), "Code", category=Category.DEEP),
            Segment(at(3), at(4), "(away)", away=True),
            Segment(at(4), at(6), "Chrome", url="https://www.youtube.com/watch", category=Category.DISTRACTION),
            Segment(at(6), at(10), "Code", category=Category.DEEP)]
INPUTS = [InputSample(at(m), at(m + 1), keys=20, clicks=5) for m in range(10)]


def value(expr, signals=(), state=None):
    return Signal("x", expr).eval(Values([*signals], Context(at(10), SEGMENTS, SEGMENTS[-1], state or {}, INPUTS)).ctx)


def test_expressions_on_primitives():
    assert value('tssum(category == "deep", 10m)') == 7  # minutes
    assert value("tssum(away, 10m)") == 1
    assert value('tscount(site == "youtube.com", 10m)') == 1
    assert value("tsmean(keys + clicks, 5m)") == 25
    assert value("tsmean(keys, 30s) > 10 and not in_session", state={"in_session": False}) is True


def test_expressions_read_other_signals_as_series():
    signals = default_signals(FocusParams())
    rise = value("focus_2m - delay(focus_2m, 2m)", signals)
    assert rise == pytest.approx(Values(signals, Context(at(10), SEGMENTS, SEGMENTS[-1]))["focus_rise"])


def test_expressions_reject_anything_else():
    for bad in ("__import__('os')", "keys.real", "[1, 2]", "nope + 1", "tsmean(keys"):
        with pytest.raises(ExprError):
            value(bad)
