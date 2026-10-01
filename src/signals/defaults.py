"""aiwa's signals, by name (what rules and pipelines can read)."""

from __future__ import annotations

from datetime import timedelta

from aiwa.core.events import Category
from aiwa.signals.base import Signal
from aiwa.signals.focus.params import FocusParams
from aiwa.signals.focus.score import Intensity, Rise
from aiwa.signals.state import OnCategory, State

STATE = ("in_session", "shutdown_done", "popup_open", "minutes_since_suggested")


def default_signals(focus: FocusParams) -> list[Signal]:
    short, main = focus.horizons[0], focus.main_horizon
    return [
        *(State(name) for name in STATE),
        Intensity("focus_2m", short, focus),
        Intensity("focus_5m", main, focus),
        Rise("focus_rise", short, timedelta(minutes=2), focus),
        OnCategory("on_deep", Category.DEEP),
    ]
