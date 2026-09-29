"""The sprint in the running app (core/sprint.py): pick the deadline for the next task,
and "time's up" at the end."""

from __future__ import annotations

from typing import Callable

from aiwa.core.backlog import Task, minutes_text
from aiwa.core.sprint import SprintParams, deadline_options
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
            self.popup.ask_text("Sprint: one task, a tight deadline. What's the task?",
                                lambda title: self._deadline(None, title) if title else None, skip_label="Cancel")
            return
        self._deadline(task, task.title)

    def _deadline(self, task: Task | None, title: str) -> None:
        estimate = f" (your estimate: {minutes_text(task.estimate)})" if task else ""
        options = deadline_options(task.estimate if task else None, self.params)
        self.popup.ask(f"Sprint on “{title}”{estimate}. Beat the clock: how long?",
                       lambda a: self.start_sprint(task, title, int(a)) if a != "cancel" else None,
                       [(f"{m} min", str(m)) for m in options] + [("Cancel", "cancel")])

    def times_up(self, title: str, on_answer: Callable[[str], None]) -> None:
        self.popup.ask(f"Time's up: “{title}”. Done?", on_answer,
                       [("Done", "done"), (f"{self.params.extension} more minutes", "more"), ("Stop", "stop")])
