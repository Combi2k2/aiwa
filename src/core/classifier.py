"""Decides when to ask the user something about what they are using.

Called every few seconds with what is in focus. Two kinds of question:

- **track**: an app not on the track list has been in focus for
  `ask_track_after`. Ask whether to track it, and as what: picking a category
  tracks and classifies it in one answer. Its name is only shown, never stored
  or sent, unless the user says yes ("Don't track" keeps just a hash).
- **classify** / **confirm**, for a tracked app or website:
  1. a config rule, an earlier user answer or a confirmed openjev answer settles it;
  2. otherwise, after `suggest_after` on it, openjev (optional) is asked in the
     background what *kind* of site or app it is (core/kinds.py); the kind and its
     default category are cached with openjev's confidence;
  3. a confident answer is shown for the user to confirm (or pick another kind, or
     let this one site count differently);
  4. with no confident answer (or "something else") after `ask_after`, the user is
     asked what it is.
  The user's answer always wins. Sites classified before kinds existed get their
  kind filled in quietly (`backfill_kinds`), without a question.
"""

from __future__ import annotations

from aiwa import platforms

from concurrent.futures import Executor, Future
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from aiwa.config import Config
from aiwa.core.events import Category, Segment
from aiwa.core.kinds import default_category
from aiwa.core.store import Classification, Store
from aiwa.core.timeline import BROWSER_APPS

Suggest = Callable[[str], "tuple[str, float] | None"]  # openjev: (kind, probability)

SUGGESTION_WAIT = timedelta(seconds=5)  # after `ask_after`, wait this long for openjev before asking without it
ASK_LATER = timedelta(hours=2)

@dataclass(frozen=True)
class Question:
    kind: str  # "track", "classify" or "confirm"
    key: str  # app name for "track"; app or website domain for "classify"


class ClassificationLoop:
    def __init__(
        self,
        config: Config,
        store: Store,
        suggest: Suggest | None,
        executor: Executor | None,
    ):
        self.config = config
        self.store = store
        self.ignore_apps = set(platforms.current().SYSTEM_APPS) | set(config.ignore_apps)  # never worth a question
        self.suggest = suggest
        self.executor = executor
        self.suggest_after = timedelta(seconds=config.suggest_after_seconds)
        self.ask_after = timedelta(seconds=config.ask_after_seconds)
        self.ask_track_after = timedelta(seconds=config.ask_track_after_seconds)
        self.current: Question | None = None
        self.since: datetime | None = None
        self.pending: dict[str, Future] = {}
        self.suggested: set[str] = set()  # keys openjev was already asked about
        self.later: dict[Question, datetime] = {}

    def observe(self, segment: Segment | None, now: datetime) -> Question | None:
        """Update with what is in focus now; return a question for the user, or None."""
        self._collect_suggestions(now)
        question = self._question_for(segment)
        if question != self.current:
            self.current, self.since = question, now
        if question is None:
            return None
        dwell = now - self.since

        if question.kind == "track":
            if dwell < self.ask_track_after or self.later.get(question, now) > now:
                return None
            return question

        key = question.key
        known = self.store.get_classification(key)
        if known and (known.source == "user" or known.confirmed):
            return None
        if dwell < self.suggest_after:
            return None  # just passing through
        if known and (known.confidence or 0) >= self.config.openjev_min_confidence:
            confirm = Question("confirm", key)
            return None if self.later.get(confirm, now) > now else confirm

        # not classified yet, or openjev was unsure
        if self.suggest and key not in self.suggested:
            self.suggested.add(key)
            self.pending[key] = self.executor.submit(self.suggest, describe(segment))
        if dwell < self.ask_after or self.later.get(question, now) > now:
            return None
        if key in self.pending and dwell < self.ask_after + SUGGESTION_WAIT:
            return None  # openjev is still thinking; give it a moment
        return question

    def answered(self, question: Question, response: str, now: datetime) -> None:
        """Responses: 'later', 'never' (track), 'ok' (confirm), 'kind:<kind>', or a category value."""
        key = question.key
        if response == "later":
            self.later[question] = now + ASK_LATER
        elif question.kind == "track" and response == "never":
            self.store.set_tracking(key, False, now)
        elif question.kind == "confirm" and response == "ok":
            self.store.confirm_category(key, now)
            known_kind = self.store.get_kind(key)
            if known_kind:
                self.store.set_kind(key, known_kind[0], "user", now)
        elif response.startswith("kind:"):
            kind = response.removeprefix("kind:")
            self.store.set_kind(key, kind, "user", now)
            category = default_category(kind)
            if category is not None:
                self.store.set_category(key, category, "user", now)
            # no default ("something else"): the app asks how it counts, answered with a category
        else:
            if question.kind == "track":  # answering with a category means "track it as this"
                self.store.set_tracking(key, True, now)
                self.config.add_tracked_apps([key])
            self.store.set_category(key, Category(response), "user", now)
            known_kind = self.store.get_kind(key)
            if known_kind and known_kind[1] == "openjev" and question.kind == "confirm":
                self.store.set_kind(key, known_kind[0], "user", now)  # the kind was right, it just counts differently

    def backfill_kinds(self) -> None:
        """Ask openjev (in the background) for the kind of sites classified before kinds existed."""
        if not self.suggest:
            return
        for key in self.store.keys_without_kind():
            if key not in self.pending and "·" not in key:
                is_site = "." in key and " " not in key
                self.suggested.add(key)
                self.pending[key] = self.executor.submit(
                    self.suggest, f"the website {key}" if is_site else f"the desktop app {key}")

    def suggestion(self, key: str) -> Classification | None:
        known = self.store.get_classification(key)
        return known if known and known.source == "openjev" else None

    def _question_for(self, segment: Segment | None) -> Question | None:
        if segment is None or segment.away or not segment.app or segment.app in self.ignore_apps:
            return None
        if not self.config.is_tracked(segment.app, segment.title, segment.url):
            if self.config.has_track_rule(segment.app):
                return None  # tracked only for some titles/URLs; the user chose that
            if self.store.get_tracking(segment.app) == "never":
                return None
            return Question("track", segment.app)
        if segment.app in BROWSER_APPS and not segment.url:
            return None  # browsers are classified per website only
        if segment.url and not segment.url.startswith(("http://", "https://")):
            return None  # browser-internal pages are neutral
        for rule in self.config.categories:
            if rule.match.matches(segment.app, segment.title, segment.url):
                return None  # the config already decides
        return Question("classify", segment.key)

    def _collect_suggestions(self, now: datetime) -> None:
        for key, future in list(self.pending.items()):
            if not future.done():
                continue
            del self.pending[key]
            result = future.result() if future.exception() is None else None
            if not result:
                continue
            kind, confidence = result
            known_kind = self.store.get_kind(key)
            if not (known_kind and known_kind[1] == "user"):
                self.store.set_kind(key, kind, "openjev", now, confidence)
            known = self.store.get_classification(key)
            category = default_category(kind)
            if category is not None and known is None:  # never overrides an existing category
                confidence = confidence if kind != "other" else 0.0
                self.store.set_category(key, category, "openjev", now, confidence)


def describe(segment: Segment) -> str:
    """What openjev sees: only the kind of activity and its app name or domain."""
    return f"the website {segment.key}" if segment.url else f"the desktop app {segment.key}"
