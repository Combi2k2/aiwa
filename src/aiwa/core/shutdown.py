"""The shutdown ritual (Deep Work, rule 1): a clear end to the workday.

At the end of the workday aiwa walks the user through closing it: today's notes
(each becomes a task or stays a note), anything still on their mind (becomes a
task, so it can be let go), a look at tomorrow, then "shutdown complete". After
that, work questions (capture) stop for the rest of the day.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

DAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


@dataclass(frozen=True)
class ShutdownParams:
    enabled: bool = True
    time: time = time(18, 0)  # the end of the workday
    days: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri")
    snooze: timedelta = timedelta(minutes=30)  # "later"


def workday(day: date, params: ShutdownParams) -> bool:
    return params.enabled and DAY_NAMES[day.weekday()] in params.days


def is_due(now: datetime, day: date, day_starts: time, params: ShutdownParams) -> bool:
    """From the shutdown time until the day ends (`day_starts` the next morning), on workdays."""
    if not workday(day, params):
        return False
    local = now.astimezone()
    end_of_work = datetime.combine(day, params.time, local.tzinfo)
    day_end = datetime.combine(day + timedelta(days=1), day_starts, local.tzinfo)
    return end_of_work <= local < day_end
