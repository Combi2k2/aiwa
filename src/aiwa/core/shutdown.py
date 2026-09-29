"""The shutdown ritual (Deep Work, rule 1): a clear end to the workday.

At the end of the workday aiwa walks the user through closing it: today's notes
(each becomes a task or stays a note), a wrap-up in their own words (anything
still open becomes a task, so it can be let go), a look at tomorrow, then
"shutdown complete". After that, work questions (capture) stop for the day.

When to offer it: a shift is ending when focus is low, and the shutdown time is
near. The two are multiplied: (how close to the shutdown time) × (how low the
focus is). Closeness is asymmetric: it rises steeply in the last hour or so
before the shutdown time and is full from then on; so it's never offered while
the user is focused, and hardly ever early in the afternoon.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

DAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


@dataclass(frozen=True)
class ShutdownParams:
    enabled: bool = True
    time: time = time(18, 0)  # the end of the workday
    days: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri")
    snooze: timedelta = timedelta(minutes=30)  # "later"
    lead: timedelta = timedelta(minutes=45)  # closeness before the shutdown time decays with this (e^-Δ/lead)
    focused: float = 0.6  # 10-min focus score counted as fully focused (the deep-minute threshold)
    offer_at: float = 0.5  # offer the shutdown once closeness × lowness reaches this


def workday(day: date, params: ShutdownParams) -> bool:
    return params.enabled and DAY_NAMES[day.weekday()] in params.days


def closeness(now: datetime, shutdown_at: datetime, lead: timedelta) -> float:
    """1 from the shutdown time on; before it e^(−time left / lead): 16:00 → 0.07, 17:00 → 0.26, 17:30 → 0.51."""
    if now >= shutdown_at:
        return 1.0
    return math.exp(-(shutdown_at - now) / lead)


def lowness(intensity: float | None, focused: float) -> float:
    """1 when not focused at all (or no data: idle, away), 0 at or above `focused`."""
    if intensity is None:
        return 1.0
    return max(0.0, 1.0 - intensity / focused)


def shift_ending(now: datetime, day: date, day_starts: time, params: ShutdownParams,
                 intensity: float | None, shutdown_time: time | None = None) -> float:
    """How strongly it looks like the workday is ending (0..1); offer the shutdown at `offer_at`."""
    if not workday(day, params):
        return 0.0
    local = now.astimezone()
    shutdown_at = datetime.combine(day, shutdown_time or params.time, local.tzinfo)
    if local >= datetime.combine(day + timedelta(days=1), day_starts, local.tzinfo):
        return 0.0
    return closeness(local, shutdown_at, params.lead) * lowness(intensity, params.focused)
