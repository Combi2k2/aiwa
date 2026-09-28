"""The running daemon: a tray app that polls, analyzes and nudges."""

from __future__ import annotations

import signal
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from platformdirs import user_log_path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from aiwa import platforms
from aiwa.config import DB_PATH, Config
from aiwa.core.analyzer import Analyzer
from aiwa.core.categories import Categorizer, prepare, summary
from aiwa.core.classifier import ClassificationLoop, Question
from aiwa.core.collector import Collector
from aiwa.core.events import Category, Finding, Level, Segment
from aiwa.core.focus import moment
from aiwa.core.openjev import Openjev
from aiwa.core.policy import NudgePolicy
from aiwa.core.rules import default_rules
from aiwa.core.store import Store
from aiwa.services.activitywatch import ActivityWatchSupervisor, find_commands, server_check
from aiwa.ui.inbox import Inbox
from aiwa.ui.popup import Popup
from aiwa.ui.tray import Tray

FAST_POLL_MS = 2_000  # how often to look at what's in focus right now (cheap: latest events only)
RATING_OPTIONS = [(c.value.capitalize(), c.value) for c in Category] + [("Ask later", "later")]
TRACK_OPTIONS = [(c.value.capitalize(), c.value) for c in Category] + [("Don't track", "never"), ("Ask later", "later")]


def _minutes(delta: timedelta) -> str:
    return f"{int(delta.total_seconds() // 60)} min"


class Aiwa:
    def __init__(self, config: Config):
        self.config = config
        self.activitywatch = start_activitywatch(config)  # before anything reads from it
        self.store = Store(DB_PATH)
        config.add_tracked_apps(self.store.tracked_apps())
        self.collector = Collector(config)
        self.categorizer = Categorizer(config.categories, self.store)
        openjev = (
            Openjev(config.openjev_api_key)
            if config.openjev_enabled and config.openjev_api_key
            else None
        )
        self.classifier = ClassificationLoop(
            config,
            self.store,
            suggest=openjev.suggest_category if openjev else None,
            executor=ThreadPoolExecutor(max_workers=2) if openjev else None,  # never block the UI on the network
        )
        self.analyzer = Analyzer(default_rules())
        self.policy = NudgePolicy(timedelta(minutes=config.min_minutes_between_nudges))
        self.tray = Tray(on_inbox=self.open_inbox, on_snooze=self.snooze_hour, on_quit=QApplication.quit)
        self.popup = Popup()
        self.inbox = Inbox(self.store)
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(config.poll_seconds * 1000)
        self.fast_timer = QTimer()
        self.fast_timer.timeout.connect(self.poll)
        self.fast_timer.start(FAST_POLL_MS)

    def tick(self) -> None:
        now = datetime.now(timezone.utc)
        if self.activitywatch:
            for module in self.activitywatch.check():
                print(f"restarted {module}", flush=True)
        try:
            raw = self.collector.timeline(timedelta(minutes=self.config.lookback_minutes))
        except (OSError, RuntimeError) as e:  # ActivityWatch not running or not ready
            self.tray.set_status(f"waiting for ActivityWatch ({e.__class__.__name__})")
            return
        segments = prepare(raw, self.config, self.categorizer)
        away = bool(segments) and max(segments, key=lambda s: s.end).away
        self.tray.set_status("away" if away else self.status(segments, now))
        for finding in self.analyzer.run(segments, now):
            if self.policy.allow(finding, now, away=away):
                self.policy.record(finding, now)
                self.show(finding, self.store.log_nudge(finding, now))

    def poll(self) -> None:
        """Every few seconds: classify what's in focus, asking the user if needed."""
        now = datetime.now(timezone.utc)
        try:
            current = self.collector.current()
        except OSError:
            return  # ActivityWatch not reachable; tick() reports it in the tray
        question = self.classifier.observe(current, now)
        if question and not self.popup.isVisible():
            self.ask(question)

    def status(self, segments: list[Segment], now: datetime) -> str:
        horizon = self.config.focus.main_horizon
        focus = moment(segments, now, horizon, self.config.focus)
        if focus.intensity is None:
            return summary(segments, self.config.lookback_minutes)
        return f"focus {focus.intensity:.2f} ({_minutes(horizon)}) · " + summary(
            segments, self.config.lookback_minutes
        )

    def ask(self, question: Question) -> None:
        if question.kind == "track":
            message = (
                f"You're using “{question.key}”, which aiwa doesn't track yet. Track it as…\n"
                "(Tracked apps are recorded by name and count toward focus;"
                " untracked ones stay anonymous.)"
            )
            options = TRACK_OPTIONS
        elif question.kind == "confirm":
            guess = self.classifier.suggestion(question.key)
            message = (
                f"“{question.key}” was classified as {guess.category.value} by openjev"
                f" ({guess.confidence or 0:.0%} sure). OK, or change it to:"
            )
            options = [("OK", "ok")] + [o for o in RATING_OPTIONS[:-1] if o[1] != guess.category.value]
        else:
            message = f"How does “{question.key}” count for you?"
            guess = self.classifier.suggestion(question.key)
            if guess:
                message += f"\n(openjev guesses {guess.category.value}, {guess.confidence or 0:.0%} sure)"
            options = RATING_OPTIONS
        self.popup.ask(
            message,
            lambda r: self.classifier.answered(question, r, datetime.now(timezone.utc)),
            options,
        )

    def show(self, finding: Finding, nudge_id: int) -> None:
        if finding.level is Level.QUIET:
            self.tray.set_status(finding.message)
        elif finding.level is Level.NOTIFY:
            self.tray.notify("aiwa", finding.message)
        else:
            self.popup.ask(finding.message, lambda r: self.on_response(nudge_id, r))

    def on_response(self, nudge_id: int, response: str) -> None:
        self.store.set_response(nudge_id, response)
        if response == "snooze":
            self.policy.snooze(datetime.now(timezone.utc) + timedelta(minutes=30))

    def open_inbox(self) -> None:
        self.inbox.open()

    def snooze_hour(self) -> None:
        self.policy.snooze(datetime.now(timezone.utc) + timedelta(hours=1))
        self.tray.set_status("snoozed for 1 hour")


def start_activitywatch(config: Config) -> ActivityWatchSupervisor | None:
    """Start ActivityWatch's programs ourselves, unless disabled, missing, or already running."""
    if not config.aw_manage:
        return None
    os_support = platforms.current()
    commands = find_commands(os_support.ACTIVITYWATCH_DIRS, os_support.EXECUTABLE_SUFFIX, config.aw_modules)
    if commands is None:
        print("ActivityWatch not found; start it yourself or set [activitywatch] manage = false", flush=True)
        return None
    supervisor = ActivityWatchSupervisor(
        commands, server_check(config.aw_host, config.aw_port), user_log_path("aiwa") / "activitywatch"
    )
    print(supervisor.start(), flush=True)
    return supervisor


def run(config: Config) -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # closing the inbox must not quit the daemon
    aiwa = Aiwa(config)
    if aiwa.activitywatch:
        app.aboutToQuit.connect(aiwa.activitywatch.stop)  # stop what we started
    # Quit cleanly (running aboutToQuit) when told to stop, e.g. at logout or by launchd.
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: app.quit())
    wake = QTimer()
    wake.timeout.connect(lambda: None)  # lets Python handle signals while Qt's loop runs
    wake.start(500)
    QTimer.singleShot(0, aiwa.tick)  # first check right away
    return app.exec()

