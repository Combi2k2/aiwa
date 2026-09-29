"""The rhythmic routine's prompts: plan tomorrow in the evening, warm-up and block
reminders in the morning. Uses the pure logic in core/schedule.py and core/rhythm.py;
this module only decides when to show which dialog and records the answers.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Callable

from aiwa.core.rhythm import Rhythm
from aiwa.core.schedule import Block, BlockReminders, Reminder, RhythmParams
from aiwa.core.store import Store
from aiwa.ui.plan_dialog import PlanDialog
from aiwa.ui.popup import Popup

PLAN_LATER = timedelta(minutes=30)  # "Later" on the planning dialog asks again after this


class RhythmPrompts:
    def __init__(
        self,
        store: Store,
        rhythm: Rhythm,
        params: RhythmParams,
        day_starts: time,
        popup: Popup,
        start_session: Callable[[], None],
    ):
        self.store = store
        self.rhythm = rhythm
        self.params = params
        self.day_starts = day_starts
        self.popup = popup
        self.start_session = start_session
        self.dialog = PlanDialog()
        self.plan_later_until: datetime | None = None
        self.reminders: BlockReminders | None = None

    # --- evening: plan tomorrow ------------------------------------------------

    def planning_due(self, now: datetime) -> bool:
        local = now.astimezone().time()
        in_evening = local >= self.params.planning_time or local < self.day_starts  # until the day ends
        if not in_evening or self.dialog.isVisible():
            return False
        if self.plan_later_until and now < self.plan_later_until:
            return False
        return self.store.get_plan(self.tomorrow(now)) is None

    def tomorrow(self, now: datetime) -> date:
        return self.rhythm.today(now) + timedelta(days=1)

    def open_planner(self, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        day = self.tomorrow(now)
        existing = self.store.get_plan(day)
        default = self.rhythm.block(day, now.astimezone().tzinfo)
        start = existing.block_start if existing else (default.start.time() if default else self.params.start)
        self.dialog.ask(
            day, start, existing.task if existing else "", existing.warmup if existing else "",
            on_save=self._save_plan,
            on_later=lambda: setattr(self, "plan_later_until", datetime.now(timezone.utc) + PLAN_LATER),
        )

    def _save_plan(self, day: date, start: time, task: str, warmup: str) -> None:
        self.store.save_plan(day, start, task, warmup, datetime.now(timezone.utc))

    # --- morning: warm-up and block ---------------------------------------------

    def todays_block(self, now: datetime) -> Block | None:
        return self.rhythm.block(self.rhythm.today(now), now.astimezone().tzinfo)

    def check_block(self, now: datetime, in_session: bool) -> None:
        """Show the warm-up or block reminder if one is due and nothing else is on screen."""
        block = self.todays_block(now)
        if block is None:
            self.reminders = None
            return
        if self.reminders is None or self.reminders.block != block:
            self.reminders = BlockReminders(block, timedelta(minutes=self.params.warmup_minutes))
            if "skipped" in self.store.block_actions(block.day):
                self.reminders.skip()
        if self.popup.isVisible():
            return
        due = self.reminders.due(now, in_session)
        if due is None:
            return
        self.reminders.shown(due)
        if due is Reminder.WARMUP:
            self.popup.ask(
                f"Warm-up time: {block.warmup}.\nYour deep-work block starts at {block.start.astimezone():%H:%M}.",
                lambda _: None,
                [("OK", "ok")],
            )
        else:
            task = f"\nToday's task: {block.task}" if block.task else ""
            self.popup.ask(
                f"It's {block.start.astimezone():%H:%M}: your deep-work block.{task}\nStart a focus session?",
                lambda answer: self._on_block_answer(answer, block),
                [("Start session", "start"), ("In 10 min", "later"), ("Skip today", "skip")],
            )

    def _on_block_answer(self, answer: str, block: Block) -> None:
        now = datetime.now(timezone.utc)
        if answer == "start":
            self.start_session()
        elif answer == "later":
            self.reminders.snooze(now)
        else:
            self.store.log_block(block.day, "skipped", now)
            self.reminders.skip()
