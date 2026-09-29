"""Work like Roosevelt (Deep Work, rule 1): a short, intense burst on one task with a
deadline tighter than feels comfortable, counting down.

The deadline is picked from a few options, the first a fraction of the task's own
estimate (tight on purpose). At the deadline: done, 5 more minutes, or stop.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class SprintParams:
    tight: float = 2 / 3  # the first option: this share of the task's estimate
    minimum: int = 10  # minutes
    options: tuple[int, ...] = (15, 25, 40)
    extension: int = 5  # "5 more minutes"


def deadline_options(estimate: int | None, params: SprintParams = SprintParams()) -> list[int]:
    """Minutes to offer, tightest first."""
    options = list(params.options)
    if estimate:
        tight = max(params.minimum, int(round(estimate * params.tight / 5)) * 5)
        options = [tight] + [m for m in options if m != tight]
    return options


@dataclass
class Sprint:
    title: str
    task_id: int | None
    ends_at: datetime
    asked: bool = False  # "time's up" is showing / was shown for this deadline

    def left(self, now: datetime) -> timedelta:
        return max(self.ends_at - now, timedelta(0))

    def due(self, now: datetime) -> bool:
        return now >= self.ends_at and not self.asked

    def extend(self, now: datetime, minutes: int) -> None:
        self.ends_at, self.asked = now + timedelta(minutes=minutes), False
