"""The morning start in the running app: today's work, the routine timer, the alarm
when the user isn't back, and the first session. Rules live in core/morning.py."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

from aiwa.core.backlog import minutes_text
from aiwa.core.morning import Action, MorningFlow
from aiwa.core.store import Store
from aiwa.ui.popup import Popup
from aiwa.ui.sound import Alarm

LATE = timedelta(hours=2)  # first activity longer ago than this (e.g. aiwa started later): not a morning anymore
ROUTINE_OPTIONS = [("15 min", "15"), ("30 min", "30"), ("45 min", "45"), ("60 min", "60"),
                   ("Start now", "now"), ("Heading out today", "out")]


class MorningPrompts:
    def __init__(
        self,
        store: Store,
        popup: Popup,
        alarm: Alarm,
        today: Callable[[datetime], object],
        first_activity: Callable[[datetime], datetime | None],
        todays_work: Callable[[datetime], str],
        request_session: Callable[[], None],
    ):
        self.store = store
        self.popup = popup
        self.alarm = alarm
        self.today = today
        self.first_activity = first_activity
        self.todays_work = todays_work
        self.request_session = request_session
        self.day = None
        self.flow = MorningFlow()

    def step(self, now: datetime, active: bool) -> None:
        day = self.today(now)
        if day != self.day:  # a new day: a fresh morning, unless it was already handled
            self.day, self.flow = day, MorningFlow()
            first = self.first_activity(now)
            if self.store.get_state(f"morning:{day}") or (first and now - first > LATE):
                self.flow.finish()
        action = self.flow.step(now, active)
        if action is Action.GREET:
            self._mark_done()  # greet once per day, even if aiwa restarts
            self.popup.ask(
                f"Good morning. {self.todays_work(now)}\n\nFirst, your morning routine: how long do you need?",
                self._routine_answer, ROUTINE_OPTIONS,
            )
        elif action is Action.ALARM:
            self.alarm.start()
            self.popup.ask(
                "Your morning routine time is up. Time to come back to the computer.",
                lambda _: None, [("I'm back", "ok")],
            )
        elif action is Action.WELCOME_BACK:
            self.alarm.stop()
            self.popup.ask(
                "Welcome back. Start your first deep-work session?",
                lambda a: self.request_session() if a == "start" else None,
                [("Start session", "start"), ("Later", "later")],
            )

    def _routine_answer(self, answer: str) -> None:
        now = datetime.now(timezone.utc)
        if answer == "now":
            self.flow.finish()
            self.request_session()
        elif answer == "out":
            self.flow.finish()
        else:
            deadline = self.flow.start_routine(now, int(answer))
            self.popup.ask(
                f"Enjoy your routine. See you back by {deadline.astimezone():%H:%M} "
                f"({minutes_text(int(answer))} + a little buffer).",
                lambda _: None, [("OK", "ok")],
            )

    def _mark_done(self) -> None:
        self.store.set_state(f"morning:{self.day}", datetime.now(timezone.utc).isoformat())
