"""Outside a session, focus is building up → "start a session?" (rules/suggest_session.py)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from aiwa.flows.base import Flow, FlowContext
from aiwa.rules.base import Cadence
from aiwa.rules.suggest_session import suggest_session
from aiwa.ui.popup import Popup


class SuggestSessionFlow(Flow):
    name = "suggest a session"

    def __init__(self, popup: Popup, start_session: Callable[[], None]):
        self.popup = popup
        self.start_session = start_session
        self.pipeline = suggest_session()
        self.cadence = Cadence(timedelta(minutes=1))
        self.last_suggested: datetime | None = None

    def minutes_since_suggested(self, now: datetime) -> float:
        """A state signal for the pipeline."""
        return (now - self.last_suggested).total_seconds() / 60 if self.last_suggested else 10_000

    def tick(self, ctx: FlowContext) -> None:
        if not self.cadence.due(ctx.now) or not self.pipeline.decide(ctx.values):
            return
        self.last_suggested = ctx.now
        self.popup.ask("You're getting into it. Start a focus session to protect this?",
                       lambda a: self.start_session() if a == "start" else None,
                       [("Start session", "start"), ("Not now", "no")])
