"""The daily routine's prompts: what needs doing tomorrow (evening), the deep-work
block (morning), planning before a session with an empty list, and handing over
tasks one at a time during a session.

The logic lives in core/ (schedule, planning, rhythm); this module only decides
when to show which window and records the answers.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Callable

from aiwa.core.planning import Assessor, DraftTask, PlanningConversation, Writer
from aiwa.core.rhythm import Rhythm
from aiwa.core.schedule import Block, BlockReminders, RhythmParams
from aiwa.core.store import Store, Todo
from aiwa.ui.plan_chat import PlanChat
from aiwa.ui.popup import Popup

PLAN_LATER = timedelta(minutes=30)  # "Later" in the evening conversation asks again after this


class RhythmPrompts:
    def __init__(
        self,
        store: Store,
        rhythm: Rhythm,
        params: RhythmParams,
        day_starts: time,
        popup: Popup,
        start_session: Callable[[], None],
        assessor: Assessor | None,
        writer: Writer | None,
    ):
        self.store = store
        self.rhythm = rhythm
        self.params = params
        self.day_starts = day_starts
        self.popup = popup
        self.start_session = start_session
        self.assessor = assessor
        self.writer = writer
        self.chat = PlanChat()
        self.plan_later_until: datetime | None = None
        self.reminders: BlockReminders | None = None

    # --- planning ------------------------------------------------------------------

    def today(self, now: datetime) -> date:
        return self.rhythm.today(now)

    def planning_day(self, now: datetime) -> date:
        """In the evening (and after midnight until the day ends) plan tomorrow, otherwise today."""
        local = now.astimezone().time()
        evening = local >= self.params.planning_time or local < self.day_starts
        return self.today(now) + timedelta(days=1 if evening else 0)

    def planning_due(self, now: datetime) -> bool:
        tomorrow = self.today(now) + timedelta(days=1)
        if self.planning_day(now) != tomorrow or self.chat.isVisible():
            return False
        if self.plan_later_until and now < self.plan_later_until:
            return False
        return self.store.todos_planned_for(tomorrow) == 0

    def open_planner(self, day: date | None = None, then: Callable[[], None] | None = None) -> None:
        now = datetime.now(timezone.utc)
        day = day or self.planning_day(now)
        carried = [t.text for t in self.store.open_todos(day)]
        conversation = PlanningConversation(day, self.assessor, self.writer)

        def save(tasks: list[DraftTask]) -> None:
            self.store.add_todos(day, [(t.text, t.kind, t.minutes) for t in tasks], datetime.now(timezone.utc))
            if then:
                then()

        def later() -> None:
            self.plan_later_until = datetime.now(timezone.utc) + PLAN_LATER

        self.chat.open(conversation, conversation.opening(carried), save, later, can_save=bool(carried))

    # --- sessions and tasks -----------------------------------------------------------

    def request_session(self) -> None:
        """Start a session, but plan first if there's nothing on today's list."""
        today = self.today(datetime.now(timezone.utc))
        if self.store.open_todos(today):
            self.start_session()
        else:
            self.open_planner(today, then=self.start_session)

    def next_task(self, now: datetime) -> Todo | None:
        tasks = self.store.open_todos(self.today(now))
        return tasks[0] if tasks else None

    def offer_task(self) -> None:
        """Hand over the next task (at session start, and after each finished one)."""
        now = datetime.now(timezone.utc)
        task = self.next_task(now)
        if task is None:
            self.popup.ask(
                "Everything on today's list is done. Add more?",
                lambda a: self.open_planner(self.today(datetime.now(timezone.utc))) if a == "add" else None,
                [("Add tasks", "add"), ("Not now", "no")],
            )
            return
        size = f"  (~{task.minutes} min)" if task.minutes else ""
        self.popup.ask(
            f"Next: {task.text}{size}",
            lambda a: self._on_task_answer(a, task),
            [("Start", "start"), ("Pick another", "another"), ("Done", "done")],
        )

    def task_done(self) -> None:
        """Tray: the current task is finished; hand over the next one."""
        task = self.next_task(datetime.now(timezone.utc))
        if task:
            self.store.set_todo_status(task.id, "done", datetime.now(timezone.utc))
        self.offer_task()

    def _on_task_answer(self, answer: str, task: Todo) -> None:
        now = datetime.now(timezone.utc)
        if answer == "done":
            self.store.set_todo_status(task.id, "done", now)
            self.offer_task()
        elif answer == "another":
            self.store.move_todo_to_end(task.id, self.today(now))
            self.offer_task()

    # --- the deep-work block -------------------------------------------------------------

    def todays_block(self, now: datetime) -> Block | None:
        return self.rhythm.block(self.today(now), now.astimezone().tzinfo)

    def check_block(self, now: datetime, in_session: bool) -> None:
        """At block time, ask to start a session (if nothing else is on screen)."""
        block = self.todays_block(now)
        if block is None:
            self.reminders = None
            return
        if self.reminders is None or self.reminders.block != block:
            self.reminders = BlockReminders(block)
            if "skipped" in self.store.block_actions(block.day):
                self.reminders.skip()
        if self.popup.isVisible() or self.chat.isVisible() or not self.reminders.due(now, in_session):
            return
        self.reminders.shown = True
        self.popup.ask(
            f"It's {block.start.astimezone():%H:%M}: your deep-work block.\nStart a focus session?",
            lambda answer: self._on_block_answer(answer, block),
            [("Start session", "start"), ("In 10 min", "later"), ("Skip today", "skip")],
        )

    def _on_block_answer(self, answer: str, block: Block) -> None:
        now = datetime.now(timezone.utc)
        if answer == "start":
            self.request_session()
        elif answer == "later":
            self.reminders.snooze(now)
        else:
            self.store.log_block(block.day, "skipped", now)
            self.reminders.skip()
