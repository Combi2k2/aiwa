"""The shutdown ritual (Deep Work, rule 1): a clear end to the workday.

At the end of the workday aiwa walks the user through closing it: today's notes
(each becomes a task or stays a note), a wrap-up in their own words (anything
still open becomes a task, so it can be let go), a look at tomorrow, then
"shutdown complete". After that, work questions (capture) stop for the day.

When to offer it: two rules (core/rule.py) that must both hold, sampled every
few minutes:
- the time of day, a soft threshold at the shutdown time (18:00 → 50%; 16:00 1%,
  17:00 10%, 17:30 25%, 18:30 75%, 19:00 90%), active from 3 hours before it;
- low focus, a soft threshold below the 5-min focus score of 0.3 (unfocused or
  idle → ~100%), active only below 0.6: never while the user is focused.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from aiwa.core.rule import AllOf, Rule, RuleParams

DAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


@dataclass(frozen=True)
class ShutdownParams:
    enabled: bool = True
    time: time = time(18, 0)  # the end of the workday: the time rule's threshold
    days: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri")
    snooze: timedelta = timedelta(minutes=30)  # "ask later"
    time_softness: timedelta = timedelta(minutes=30 / math.log(3))  # ±30 min → 25% / 75%
    time_from: timedelta = timedelta(hours=3)  # the time rule is active from this long before the shutdown time
    focus_threshold: float = 0.3  # low focus: 50% here (5-min focus score)
    focus_softness: float = 0.07  # 0.15 → 89%, 0.45 → 11%
    focused: float = 0.6  # at or above this the user is focused: never offered
    check_every: timedelta = timedelta(minutes=5)


def workday(day: date, params: ShutdownParams) -> bool:
    return params.enabled and DAY_NAMES[day.weekday()] in params.days


@dataclass(frozen=True)
class ShiftContext:
    now: datetime
    day: date  # the "day" now belongs to (before day_starts = the previous one)
    day_starts: time
    intensity: float | None  # 5-min focus score; None = no data (idle, away)


class TimeRule(Rule[ShiftContext]):
    """Minutes past the shutdown time (negative before it)."""

    def __init__(self, params: ShutdownParams):
        super().__init__(RuleParams(threshold=0, softness=params.time_softness.total_seconds() / 60,
                                    range=(-params.time_from.total_seconds() / 60, None)))
        self.shutdown = params

    def measure(self, c: ShiftContext) -> float:
        local = c.now.astimezone()
        return (local - datetime.combine(c.day, self.shutdown.time, local.tzinfo)).total_seconds() / 60

    def active(self, c: ShiftContext) -> bool:
        local = c.now.astimezone()
        before_day_end = local < datetime.combine(c.day + timedelta(days=1), c.day_starts, local.tzinfo)
        return workday(c.day, self.shutdown) and before_day_end


class LowFocusRule(Rule[ShiftContext]):
    """The 5-min focus score, firing below the threshold; no data counts as unfocused."""

    def __init__(self, params: ShutdownParams):
        super().__init__(RuleParams(threshold=params.focus_threshold, softness=params.focus_softness,
                                    direction=-1, range=(None, params.focused - 1e-9)))

    def measure(self, c: ShiftContext) -> float:
        return 0.0 if c.intensity is None else c.intensity


def shift_ending(params: ShutdownParams) -> AllOf[ShiftContext]:
    """The rule for offering the shutdown: near/after the shutdown time, and focus low."""
    return AllOf(TimeRule(params), LowFocusRule(params))
