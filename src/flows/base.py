"""Flows: what aiwa does over time, each a sequence of actions (popups, alarms, records).

A `Flow` reacts to two clocks; both hooks do nothing unless a flow overrides them:

- `tick(ctx)`: every 15 seconds, with the recent timeline (sessions, morning,
  bedtime, reminders, budget, shutdown offer, ...);
- `poll(ctx)`: every 2 seconds, with what's in focus right now (capture, slips,
  hub-and-spoke, moving the shutdown ritual on, ...).

Flows can also be started by the user (tray items) or by another flow; those
entry points are ordinary methods of each flow.

`FlowContext` extends the signals' `Context` with what flows need to decide: who is
active, the session, what's in focus now, and the lazily evaluated signal values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from aiwa.core.events import Category, Segment
from aiwa.signals.base import Context, Values


@dataclass
class FlowContext(Context):
    active: bool = False  # at the computer now (recent input, not away)
    away_since: datetime | None = None  # the last input before the current absence (None while active)
    in_session: bool = False
    current: Segment | None = None  # poll: what's in focus right now (or away)
    category: Category | None = None  # poll: how `current` counts
    kind: str | None = None  # poll: what `current` is (core/kinds.py)
    values: Values | None = field(default=None, repr=False)  # the signals (tick)


class Flow:
    name: str = "flow"

    def tick(self, ctx: FlowContext) -> None:
        """Every tick (15 s)."""

    def poll(self, ctx: FlowContext) -> None:
        """Every poll (2 s)."""
