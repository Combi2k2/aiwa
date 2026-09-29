"""The shutdown ritual (Deep Work, rule 1): a clear end to the workday.

At the end of the workday aiwa walks the user through closing it: today's notes
(each becomes a task or stays a note), a wrap-up in their own words (anything
still open becomes a task, so it can be let go), a look at tomorrow, then
"shutdown complete". After that, work questions (capture) stop for the day.

When to offer it: a shift is ending when focus is low, and it's around or past
the shutdown time. The two are multiplied: (time weight) × (how low the focus
is). The time weight is an S-curve centred on the shutdown time (18:00): 16:00
and 17:00 low, 17:30 low-mid, 18:00 mid, 18:30 high-mid, 19:00 high. Focus
weight: high when focus is low, 0 when focused, so it's never offered then.
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
    spread: timedelta = timedelta(minutes=30 / math.log(3))  # S-curve width: ±30 min from the shutdown time → 0.25 / 0.75
    focused: float = 0.6  # 10-min focus score counted as fully focused (the deep-minute threshold)
    offer_at: float = 0.5  # offer the shutdown once closeness × lowness reaches this


def workday(day: date, params: ShutdownParams) -> bool:
    return params.enabled and DAY_NAMES[day.weekday()] in params.days


def time_weight(now: datetime, shutdown_at: datetime, spread: timedelta) -> float:
    """Logistic S-curve around the shutdown time: 16:00 0.01, 17:00 0.1, 17:30 0.25, 18:00 0.5, 18:30 0.75, 19:00 0.9."""
    x = (now - shutdown_at) / spread
    return 1 / (1 + math.exp(-x)) if x > -50 else 0.0


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
    return time_weight(local, shutdown_at, params.spread) * lowness(intensity, params.focused)
