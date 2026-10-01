from datetime import datetime, timedelta, timezone

from aiwa.core.events import Category, Segment
from aiwa.rules.suggest_session import suggest_session
from aiwa.signals.base import Context, Signal, Values
from aiwa.signals.defaults import default_signals
from aiwa.signals.focus.params import FocusParams

T0 = datetime(2026, 10, 1, 10, tzinfo=timezone.utc)


def at(minutes):
    return T0 + timedelta(minutes=minutes)


class Counting(Signal):
    name = "counting"
    calls = 0

    def eval(self, ctx):
        Counting.calls += 1
        return 42


def test_values_are_lazy_and_cached():
    values = Values([Counting()], Context(T0))
    assert Counting.calls == 0
    assert values["counting"] == 42 and values.get("counting") == 42 and Counting.calls == 1


def test_default_signals_feed_the_suggest_session_pipeline():
    # distracted until minute 6, then 4 minutes of deep work: focus is building up
    segments = [Segment(at(0), at(6), "Chrome", url="https://youtube.com/", category=Category.DISTRACTION),
                Segment(at(6), at(10), "Code", category=Category.DEEP)]
    state = {"in_session": False, "shutdown_done": False, "popup_open": False, "minutes_since_suggested": 999}
    values = Values(default_signals(FocusParams()), Context(at(10), segments, segments[-1], state))
    assert values["on_deep"] is True and values["focus_rise"] > 0.15
    assert suggest_session().decide(values)
