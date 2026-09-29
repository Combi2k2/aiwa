"""Productive meditation (Deep Work, rule 2): a walk spent thinking through one
well-defined problem.

After a good session aiwa sometimes suggests one (and the tray can start one any
time). The walk is a focus session on an offline "task" (the problem): being
away is the work, and it counts as deep minutes, up to its length (+ the usual
grace). Back at the computer, the user writes down what they figured out.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from aiwa.core.backlog import Task

WALK_TASK_ID = -1  # not in the backlog


@dataclass(frozen=True)
class MeditationParams:
    chance: float = 0.5  # after a good session, suggest a walk this often
    min_deep_minutes: int = 25  # a "good session": at least this much deep work
    lengths: tuple[int, ...] = (15, 30, 45)  # minutes to choose from


def should_suggest(session_deep_minutes: int, params: MeditationParams, rng: random.Random) -> bool:
    return session_deep_minutes >= params.min_deep_minutes and rng.random() < params.chance


def walk_task(problem: str, minutes: int) -> Task:
    """The walk as an offline task, so the session treats time away as the work."""
    return Task(WALK_TASK_ID, None, None, problem, "", None, minutes, kind="deep", offline=True)


def is_walk(task: Task | None) -> bool:
    return task is not None and task.id == WALK_TASK_ID
