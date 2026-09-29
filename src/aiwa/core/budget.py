"""The shallow-work budget (Deep Work, rule 4): how much of the day goes to shallow work.

Like every limit in aiwa it's a soft threshold: nothing happens at the line.
aiwa measures how far over it the user is and, every so often, samples whether
to say something; the further over, the more likely.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta

AWAY = {"away"}


@dataclass(frozen=True)
class BudgetParams:
    limit: float = 0.30  # share of active time that may go to shallow work
    scale: float = 0.15  # chance of a prompt per check = 1 − e^(−overshoot / scale): +5 pts 28%, +10 49%, +20 74%
    check_every: timedelta = timedelta(minutes=30)
    min_active: timedelta = timedelta(hours=1)  # too early in the day to judge before this


@dataclass(frozen=True)
class ShallowShare:
    shallow: int  # minutes
    active: int  # minutes at the computer (not away)

    @property
    def share(self) -> float:
        return self.shallow / self.active if self.active else 0.0


def shallow_share(minutes_by_activity: dict[str, int]) -> ShallowShare:
    active = sum(m for activity, m in minutes_by_activity.items() if activity not in AWAY)
    return ShallowShare(minutes_by_activity.get("shallow", 0), active)


def prompt_probability(share: float, params: BudgetParams) -> float:
    overshoot = share - params.limit
    return 0.0 if overshoot <= 0 else 1 - math.exp(-overshoot / params.scale)


class ShallowBudget:
    """Every `check_every`, samples whether to mention the budget."""

    def __init__(self, params: BudgetParams = BudgetParams(), rng: random.Random | None = None):
        self.params = params
        self.rng = rng or random.Random()
        self.last_check: datetime | None = None

    def should_prompt(self, now: datetime, today: ShallowShare) -> bool:
        if today.active < self.params.min_active.total_seconds() / 60:
            return False
        if self.last_check is not None and now - self.last_check < self.params.check_every:
            return False
        self.last_check = now
        return self.rng.random() < prompt_probability(today.share, self.params)
