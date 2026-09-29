"""The shutdown ritual in the running app: today's notes → anything on your mind →
tomorrow → "shutdown complete". Timing lives in core/shutdown.py.

The steps run one after another whenever no popup or task window is open, so
cancelling a task form just moves on to the next step.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Callable

from aiwa.core.scoreboard.day import day_bounds
from aiwa.core.shutdown import ShutdownParams, is_due
from aiwa.core.store import Store
from aiwa.tasks_controller import TasksController
from aiwa.ui.popup import Popup


class ShutdownPrompts:
    def __init__(self, store: Store, popup: Popup, tasks: TasksController, params: ShutdownParams,
                 day_starts: time, wrap_up: Callable[[datetime], str]):
        self.store = store
        self.popup = popup
        self.tasks = tasks
        self.params = params
        self.day_starts = day_starts
        self.wrap_up = wrap_up  # today's deep work and tomorrow's start, for the last step
        self.snoozed_until: datetime | None = None
        self.stage: str | None = None  # 'notes', 'mind', 'tomorrow' while the ritual runs
        self.notes: list[tuple[int, str, str | None]] = []
        self.mind_asked = False

    def _key(self, now: datetime) -> str:
        return f"shutdown:{day_bounds(now, self.day_starts)[0].isoformat()}"

    def done_today(self, now: datetime) -> bool:
        """The workday is shut down (or the ritual is under way): no more work questions today."""
        return self.store.get_state(self._key(now)) is not None

    def _busy(self) -> bool:
        return self.popup.isVisible() or self.tasks.form.isVisible() or self.tasks.breakdown_dialog.isVisible()

    def step(self, now: datetime, active: bool, in_session: bool) -> None:
        """Every poll (a few seconds)."""
        if self._busy():
            return
        if self.stage is not None:
            self._next(now)
            return
        day = day_bounds(now, self.day_starts)[0]
        if (not active or in_session or not is_due(now, day, self.day_starts, self.params)
                or self.done_today(now) or (self.snoozed_until and now < self.snoozed_until)):
            return
        self.popup.ask(
            "Time to shut down the workday: go through today's notes, write down what's still on your mind, look at tomorrow.",
            lambda a: self._start(now) if a == "start" else self._snooze(now),
            [("Start shutdown", "start"), ("Later (30 min)", "later")],
        )

    def _snooze(self, now: datetime) -> None:
        self.snoozed_until = now + self.params.snooze

    def _start(self, now: datetime) -> None:
        self.store.set_state(self._key(now), "started")
        self.notes = self.store.notes_to_review(now)
        self.stage, self.mind_asked = "notes", False
        self._next(now)

    def _next(self, now: datetime) -> None:
        if self.stage == "notes":
            if self.notes:
                note_id, text, source = self.notes.pop(0)
                self.popup.ask(
                    f"Today's note: “{text}”" + (f"\n(from {source})" if source else ""),
                    lambda a: self._note_answer(a, note_id, text),
                    [("Make it a task", "task"), ("Keep as note", "keep")],
                )
                return
            self.stage = "mind"
        if self.stage == "mind":
            message = ("Anything else?" if self.mind_asked else
                       "Anything still on your mind for work? Write it down as a task so you can let it go.")
            self.mind_asked = True
            self.popup.ask_text(message, self._mind_answer, placeholder="something to do…", skip_label="That's all")
            return
        if self.stage == "tomorrow":
            self.stage = None
            self.popup.ask(self.wrap_up(now), lambda _: self._complete(now), [("Shutdown complete", "done")])

    def _note_answer(self, answer: str, note_id: int, text: str) -> None:
        self.store.mark_note_reviewed(note_id)
        if answer == "task":
            self.tasks.new_task(title=text, on_added=lambda task_id: self.store.link_note(note_id, task_id))

    def _mind_answer(self, text: str | None) -> None:
        if text is None:
            self.stage = "tomorrow"
        else:
            self.tasks.new_task(title=text)  # after the form: "anything else?"

    def _complete(self, now: datetime) -> None:
        self.store.set_state(self._key(now), "done")
