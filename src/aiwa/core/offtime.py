"""The user's usual "off time": when they typically stop using the computer at the
end of the workday, learned from their absences.

Off time = the peak of the distribution (smoothed, time of day) of absence starts
of 30+ minutes, looked for around the shutdown time only (so lunch doesn't count).
It is used to catch the end of the workday before the user is gone:
- a session ending near the off time → remind them to wrap up the day;
- wrap-ups often missed → around the off time, offer an alarm for the wrap-up.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, time, timedelta


@dataclass(frozen=True)
class OffTimeParams:
    min_absence: timedelta = timedelta(minutes=30)  # shorter breaks aren't stopping
    bandwidth: timedelta = timedelta(minutes=30)  # smoothing of the distribution
    before: timedelta = timedelta(hours=3)  # look for the peak from this long before the shutdown time
    after: timedelta = timedelta(hours=4)  # ... until this long after it
    min_days: int = 5  # days with a stop in that window needed before trusting the peak
    near: timedelta = timedelta(minutes=30)  # a session ending this close to the off time → wrap-up reminder
    missed_days: int = 5  # look at the last this many workdays ...
    missed_at_least: int = 3  # ... wrap-up missed this often → offer an alarm
    offer_every: timedelta = timedelta(days=7)  # offer the alarm at most this often


def _minute_of_day(t: time) -> float:
    return t.hour * 60 + t.minute


def off_time(stops: list[datetime], shutdown_time: time, params: OffTimeParams = OffTimeParams()) -> time | None:
    """The peak of stop times near the shutdown time, or None with too few days of data."""
    center = _minute_of_day(shutdown_time)
    lo = center - params.before.total_seconds() / 60
    hi = center + params.after.total_seconds() / 60
    band = params.bandwidth.total_seconds() / 60
    minutes, days = [], set()
    for stop in stops:
        local = stop.astimezone()
        m = _minute_of_day(local.time())
        if lo - 2 * band <= m <= hi + 2 * band:
            minutes.append(m)
            if lo <= m <= hi:
                days.add(local.date())
    if len(days) < params.min_days:
        return None
    best, best_density = None, -1.0
    m = lo
    while m <= hi:
        density = sum(math.exp(-0.5 * ((m - x) / band) ** 2) for x in minutes)
        if density > best_density:
            best, best_density = m, density
        m += 5
    best = int(best) % (24 * 60)
    return time(best // 60, best % 60)


def near(now: datetime, off: time | None, params: OffTimeParams = OffTimeParams()) -> bool:
    if off is None:
        return False
    local = now.astimezone()
    return abs(datetime.combine(local.date(), off, local.tzinfo) - local) <= params.near


def often_missed(done: list[bool], params: OffTimeParams = OffTimeParams()) -> bool:
    """`done`: whether the wrap-up was done, for recent workdays (newest first)."""
    recent = done[: params.missed_days]
    return sum(1 for d in recent if not d) >= params.missed_at_least
