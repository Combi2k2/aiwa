"""The morning start: from picking up the laptop to the first deep-work session.

1. The first activity of the day → show today's work and ask how long the morning
   routine takes (or "start now" / "heading out today").
2. The routine gets that time plus a buffer: clamp(20% of it, 5, 20) minutes.
3. Back at the computer after having stepped away → suggest the first session.
   Not back by the deadline → the alarm rings until the user is back, then the same.
   Still at the computer when the deadline passes → just suggest the session.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

LEFT_AFTER = timedelta(minutes=3)  # away at least this long during the routine = actually went to do it


def buffer_for(routine: timedelta) -> timedelta:
    """clamp(20% of the routine, 5, 20) minutes."""
    minutes = min(max(routine.total_seconds() / 60 * 0.2, 5), 20)
    return timedelta(minutes=minutes)


class State(Enum):
    WAITING = "waiting"  # no activity yet today
    ASKED = "asked"  # the morning popup is showing
    ROUTINE = "routine"  # doing the morning routine
    DONE = "done"  # session suggested, skipped, or heading out


class Action(Enum):
    NONE = "none"
    GREET = "greet"  # first activity: show today's work, ask about the routine
    ALARM = "alarm"  # routine deadline passed and the user isn't back
    WELCOME_BACK = "welcome_back"  # back (or time's up at the computer): suggest the first session


@dataclass
class MorningFlow:
    state: State = State.WAITING
    deadline: datetime | None = None
    away_since: datetime | None = None
    left: bool = False  # stepped away long enough during the routine
    ringing: bool = False

    def step(self, now: datetime, active: bool) -> Action:
        if self.state is State.WAITING:
            if active:
                self.state = State.ASKED
                return Action.GREET
            return Action.NONE
        if self.state is not State.ROUTINE:
            return Action.NONE

        if not active:
            self.away_since = self.away_since or now
            if now - self.away_since >= LEFT_AFTER:
                self.left = True
            if now >= self.deadline and not self.ringing:
                self.ringing = True
                return Action.ALARM
            return Action.NONE
        self.away_since = None
        if self.ringing or self.left or now >= self.deadline:  # back, or time's up while still here
            self.state = State.DONE
            self.ringing = False
            return Action.WELCOME_BACK
        return Action.NONE

    def start_routine(self, now: datetime, minutes: int) -> datetime:
        routine = timedelta(minutes=minutes)
        self.state = State.ROUTINE
        self.deadline = now + routine + buffer_for(routine)
        self.away_since, self.left, self.ringing = None, False, False
        return self.deadline

    def finish(self) -> None:
        """Start now, heading out, or the session was suggested: nothing more this morning."""
        self.state = State.DONE
        self.ringing = False
