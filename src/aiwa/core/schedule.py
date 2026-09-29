"""The rhythmic deep-work block: the same time every day, so it becomes a habit.

Each day's block comes from the evening plan for that day if there is one,
otherwise from the default rhythm in the settings. `BlockReminders` decides when
to remind the user: a warm-up before the block (if one was planned), then the
block itself ("start a focus session?"), with "in 10 minutes" and "skip today".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import Enum

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


@dataclass(frozen=True)
class RhythmParams:
    days: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri")
    start: time = time(9, 0)
    minutes: int = 90
    planning_time: time = time(21, 30)  # when to ask for tomorrow's plan
    warmup_minutes: int = 20  # warm-up reminder this long before the block
    kept_deep_minutes: int = 25  # a block counts as kept with this much deep work in it


@dataclass(frozen=True)
class Plan:
    """What the user decided the evening before."""

    day: date
    block_start: time
    task: str = ""
    warmup: str = ""


@dataclass(frozen=True)
class Block:
    day: date
    start: datetime
    end: datetime
    task: str = ""
    warmup: str = ""


def block_for(day: date, params: RhythmParams, plan: Plan | None, tz) -> Block | None:
    """The day's block: from the plan if made, else from the rhythm (None on days off)."""
    if plan is None and WEEKDAYS[day.weekday()] not in params.days:
        return None
    start_time = plan.block_start if plan else params.start
    start = datetime.combine(day, start_time, tz)
    return Block(
        day=day,
        start=start,
        end=start + timedelta(minutes=params.minutes),
        task=plan.task if plan else "",
        warmup=plan.warmup if plan else "",
    )


class Reminder(Enum):
    WARMUP = "warmup"
    START = "start"


@dataclass
class BlockReminders:
    """Which reminder is due for a block. One instance per day's block."""

    block: Block
    warmup_before: timedelta
    snoozed_until: datetime | None = None
    done: set[Reminder] = field(default_factory=set)  # shown, answered, or no longer relevant

    def due(self, now: datetime, in_session: bool) -> Reminder | None:
        if in_session or now >= self.block.end:
            return None  # already working, or the block is over
        if self.snoozed_until and now < self.snoozed_until:
            return None
        if Reminder.START not in self.done and now >= self.block.start:
            return Reminder.START
        warmup_at = self.block.start - self.warmup_before
        if self.block.warmup and Reminder.WARMUP not in self.done and warmup_at <= now < self.block.start:
            return Reminder.WARMUP
        return None

    def shown(self, reminder: Reminder) -> None:
        self.done.add(reminder)

    def snooze(self, now: datetime, minutes: int = 10) -> None:
        """Ask again later: the start reminder comes back after `minutes`."""
        self.done.discard(Reminder.START)
        self.snoozed_until = now + timedelta(minutes=minutes)

    def skip(self) -> None:
        self.done.update({Reminder.WARMUP, Reminder.START})
