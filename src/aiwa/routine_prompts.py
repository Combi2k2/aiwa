"""Routine questions in the running app: after an absence, sometimes ask what it was.

Every absence is stored (asked or not); overnight ones are logged as sleep. The
question offers the likely activities first, then "Other…" (categories → their
activities) and "Skip". Rules live in core/routines.py.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from aiwa.core.backlog import minutes_text
from aiwa.core.routines import ACTIVITY_LABEL, TAXONOMY, Absence, AbsenceTracker, likely_activities, overnight
from aiwa.core.store import Store
from aiwa.ui.popup import Popup

STALE = timedelta(minutes=30)  # a question not asked within this long (popup busy) is dropped


class RoutinePrompts:
    def __init__(self, store: Store, popup: Popup, bedtime: time, day_starts: time, always_ask: bool = False):
        self.store = store
        self.popup = popup
        self.bedtime = bedtime
        self.day_starts = day_starts
        self.tracker = AbsenceTracker(always_ask=always_ask)
        self.pending: tuple[int, Absence] | None = None  # waiting for the popup to be free
        self.offline_task = False  # the absence ending now was work on an offline task: don't ask

    def offline_work_done(self) -> None:
        """The user is back from working on an offline task (called before `step`)."""
        self.offline_task = True

    def step(self, now: datetime, active: bool, away_since: datetime | None = None) -> None:
        absence = self.tracker.step(now, active, away_since)
        if absence is not None:
            if self.offline_task:
                self.store.add_absence(absence.start, absence.end, "offline_task", "session")
            elif overnight(absence, self.bedtime, self.day_starts):
                self.store.add_absence(absence.start, absence.end, "sleep", "auto")
            elif self.tracker.should_ask(absence):
                self.pending = (self.store.add_absence(absence.start, absence.end, None, "unasked"), absence)
            else:
                self.store.add_absence(absence.start, absence.end, None, "unasked")
        if active:
            self.offline_task = False
        if self.pending and not self.popup.isVisible():
            absence_id, absence = self.pending
            self.pending = None
            if now - absence.end <= STALE:
                self._ask(absence_id, absence)

    def _ask(self, absence_id: int, absence: Absence) -> None:
        options = [(ACTIVITY_LABEL[a], a) for a in likely_activities(absence.duration, absence.start)]
        self.popup.ask(
            f"You were away for {minutes_text(int(absence.duration.total_seconds() // 60))}. What was that?",
            lambda answer: self._answer(absence_id, answer),
            options + [("Other…", "other"), ("Skip", "skip")],
        )

    def _answer(self, absence_id: int, answer: str) -> None:
        if answer == "skip":
            self.store.set_absence_activity(absence_id, None, "skipped")
        elif answer == "other":
            self.popup.ask(
                "Which kind of thing?",
                lambda category: self._pick_in(absence_id, category),
                [(label, key) for key, (label, _) in TAXONOMY.items()],
            )
        else:
            self.store.set_absence_activity(absence_id, answer, "user")

    def _pick_in(self, absence_id: int, category: str) -> None:
        _, items = TAXONOMY[category]
        self.popup.ask("Which one?", lambda answer: self._answer(absence_id, answer), [(label, key) for key, label in items])
