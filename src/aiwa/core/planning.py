"""Turning the user's own list into atomic tasks, each doable in one focus session.

The user writes the plan; aiwa never invents tasks. A conversation:

1. The user lists what needs doing (free text).
2. The list is split into separate tasks (the AI, or one task per line).
3. Each task is assessed (openjev): deep or shallow, estimated size, specific or vague.
4. A task needs elaboration if it is vague / can't be sized, or likely takes more
   than one session (50 min). aiwa asks one short question about it (the AI writes
   the question, or a template does), and the user's answer becomes smaller tasks.
5. Repeat until every task is atomic, then save.

Every outside service is optional: without the AI the wording comes from
templates, without openjev every task is accepted as the user wrote it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

MAX_ROUNDS = 2  # ask about the same task at most this often, then accept it as the user wrote it


@dataclass(frozen=True)
class Assessment:
    kind: str | None  # 'deep' or 'shallow'
    minutes: int | None  # estimated size; None = can't be told
    specific: float  # 0..1: concrete scope and a clear end point?

    @property
    def needs_elaboration(self) -> str | None:
        """'vague', 'too_long' or None (atomic: fine as it is)."""
        if self.minutes is None or self.specific < SPECIFIC_ENOUGH:
            return "vague"
        if self.minutes > SESSION_MINUTES:
            return "too_long"
        return None


SPECIFIC_ENOUGH = 0.5
SESSION_MINUTES = 50  # the longest a single task may take: one deep-work session


class Assessor(Protocol):
    def __call__(self, task: str) -> Assessment | None: ...


class Writer(Protocol):
    """The conversational part (an AI model). Every method may return None when unavailable."""

    def split(self, text: str) -> list[str] | None: ...
    def question(self, task: str, reason: str) -> str | None: ...
    def refine(self, task: str, question: str, answer: str) -> list[str] | None: ...


@dataclass
class DraftTask:
    text: str
    kind: str | None = None
    minutes: int | None = None
    rounds: int = 0  # how often the user was asked about it
    reason: str | None = None  # why it needs elaboration: 'vague' or 'too_long'


@dataclass
class Reply:
    messages: list[str]
    done: bool  # nothing left to ask; the plan can be saved


@dataclass
class PlanningConversation:
    day: date
    assessor: Assessor | None
    writer: Writer | None
    accepted: list[DraftTask] = field(default_factory=list)
    pending: list[DraftTask] = field(default_factory=list)
    asking: DraftTask | None = None
    question_text: str = ""

    def opening(self, carried_over: list[str]) -> str:
        text = f"What needs to be done on {self.day:%A}? List everything, one per line."
        if carried_over:
            text += "\n\nStill open from before (already on the list):\n" + "\n".join(f"• {t}" for t in carried_over)
        return text

    def receive(self, text: str) -> Reply:
        """Handle one message from the user (blocking: may call openjev and the AI)."""
        text = text.strip()
        if not text:
            return self._next()
        if self.asking is not None:
            task, self.asking = self.asking, None
            if text.lower() in ("keep", "skip", "it's fine", "fine", "ok"):
                self.accepted.append(task)  # the user decides: keep it as it is
            else:
                parts = self._call(lambda w: w.refine(task.text, self.question_text, text)) or split_lines(text)
                self._assess([DraftTask(p, rounds=task.rounds + 1) for p in parts])
            return self._next()
        parts = self._call(lambda w: w.split(text)) or split_lines(text)
        self._assess([DraftTask(p) for p in parts])
        return self._next()

    def _assess(self, drafts: list[DraftTask]) -> None:
        for draft in drafts:
            assessment = self.assessor(draft.text) if self.assessor else None
            if assessment is not None:
                draft.kind, draft.minutes = assessment.kind, assessment.minutes
            draft.reason = assessment.needs_elaboration if assessment else None
            if draft.reason and draft.rounds < MAX_ROUNDS:
                self.pending.append(draft)
            else:
                self.accepted.append(draft)

    def _next(self) -> Reply:
        if self.pending:
            task = self.asking = self.pending.pop(0)
            reason = task.reason or "vague"
            self.question_text = self._call(lambda w: w.question(task.text, reason)) or template_question(task.text, reason)
            return Reply([self.question_text], done=False)
        if not self.accepted:
            return Reply(["Nothing on the list yet. What needs to be done?"], done=False)
        summary = "\n".join(f"{i}. {t.text}" + (f"  (~{t.minutes} min, {t.kind})" if t.minutes else "")
                            for i, t in enumerate(self.accepted, 1))
        return Reply([f"Here's the plan:\n{summary}\n\nAdd more below, or save it."], done=True)

    def _call(self, fn):
        if self.writer is None:
            return None
        try:
            return fn(self.writer)
        except Exception:  # the AI is optional: any failure falls back to the templates
            return None


def split_lines(text: str) -> list[str]:
    """One task per line (bullets and numbering removed)."""
    parts = []
    for line in text.splitlines():
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
        if line:
            parts.append(line)
    return parts


def template_question(task: str, reason: str) -> str:
    if reason == "too_long":
        return (f"“{task}” looks like more than one focus session (over 50 min). "
                "What are the steps? One per line, each doable in under 50 minutes.")
    return (f"“{task}” is hard to size. What exactly does it involve (which part, how much)? "
            "One concrete step per line. Or type “keep” to leave it as it is.")
