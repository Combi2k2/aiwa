"""The evening wind-down in the running app: pokes, "10 more minutes", the alarm,
and a simple sleep log (last activity at night, first activity in the morning).

The rules live in core/bedtime.py; this module shows popups and rings the alarm.
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Callable

from aiwa.core.bedtime import Action, BedtimeParams, WindDown
from aiwa.core.store import Store
from aiwa.ui.popup import Popup
from aiwa.ui.sound import Alarm


class BedtimePrompts:
    def __init__(self, store: Store, params: BedtimeParams, day_starts: time, popup: Popup, alarm: Alarm,
                 lock_screen: Callable[[], None], today: Callable[[datetime], object]):
        self.store = store
        self.day_starts = day_starts
        self.popup = popup
        self.alarm = alarm
        self.lock_screen = lock_screen
        self.today = today
        self.wind_down = WindDown(params, day_starts)

    def step(self, now: datetime, active: bool) -> None:
        if active:
            self._log(now)
        action = self.wind_down.step(now, active)
        local = now.astimezone()
        if action is Action.POKE:
            options = [("OK, winding down", "ok"), ("Lock screen", "lock")]
            if not self.wind_down.snooze_used:
                options.insert(0, ("10 more minutes", "snooze"))
            self.popup.ask(
                f"It's {local:%H:%M}. Time to wrap up and get ready for bed.\n"
                "Ending the day on time is how you take back control of tomorrow.",
                self._answer, options,
            )
        elif action is Action.ALARM:
            self.alarm.start()
            self.popup.ask(
                f"It's {local:%H:%M}, past your stop time. The alarm keeps ringing while you're still here.\n"
                "Lock the screen and go to sleep.",
                self._answer, [("Lock screen", "lock")],
            )
        elif action is Action.SILENCE:
            self.alarm.stop()

    def _answer(self, response: str) -> None:
        if response == "snooze":
            self.wind_down.snooze(datetime.now(timezone.utc))
        elif response == "lock":
            self.lock_screen()

    # --- sleep log -------------------------------------------------------------------------

    def _log(self, now: datetime) -> None:
        day = self.today(now).isoformat()
        self.store.set_state(f"last_active:{day}", now.isoformat())
        if self.store.get_state(f"first_active:{day}") is None:
            self.store.set_state(f"first_active:{day}", now.isoformat())

    def last_night(self, now: datetime) -> tuple[datetime | None, datetime | None]:
        """(last activity of the previous day, first activity today)."""
        from datetime import timedelta

        today = self.today(now)
        off = self.store.get_state(f"last_active:{(today - timedelta(days=1)).isoformat()}")
        up = self.store.get_state(f"first_active:{today.isoformat()}")
        return (datetime.fromisoformat(off) if off else None, datetime.fromisoformat(up) if up else None)
