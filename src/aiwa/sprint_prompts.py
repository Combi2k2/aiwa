"""The sprint in the running app (core/sprint.py): pick the deadline for the next task,
and "time's up" at the end."""

from __future__ import annotations

from typing import Callable

from aiwa.core.backlog import Task
from aiwa.core.sprint import SprintParams
from aiwa.ui.popup import Popup


class SprintPrompts:
    def __init__(self, popup: Popup, start_sprint: Callable[[Task | None, str, int], None],
                 next_task: Callable[[], Task | None], params: SprintParams = SprintParams()):
        self.popup = popup
        self.start_sprint = start_sprint  # (task, title, minutes)
        self.next_task = next_task
        self.params = params

    def start(self) -> None:
        task = self.next_task()
        if task is None:
            self.popup.ask_text("Sprint: one task, against the clock. What's the task?",
                                lambda title: self._deadline(title) if title else None, skip_label="Cancel")
            return
        self.start_sprint(task, task.title, task.estimate)  # the deadline is your own estimate

    def _deadline(self, title: str) -> None:
        self.popup.ask(f"Sprint on “{title}”. Beat the clock: how long?",
                       lambda a: self.start_sprint(None, title, int(a)) if a != "cancel" else None,
                       [(f"{m} min", str(m)) for m in self.params.options] + [("Cancel", "cancel")])

    def times_up(self, title: str, on_answer: Callable[[str], None]) -> None:
        self.popup.ask(f"Time's up: “{title}”. Done?", on_answer,
                       [("Done", "done"), (f"{self.params.extension} more minutes", "more"), ("Stop", "stop")])
