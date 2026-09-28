"""The running daemon: a tray app that polls, analyzes and nudges."""

from __future__ import annotations

import signal
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from platformdirs import user_log_path
from PySide6.QtCore import QLockFile, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication

from aiwa import platforms
from aiwa.config import CONFIG_PATH, DATA_DIR, DB_PATH, Config
from aiwa.core.analyzer import Analyzer
from aiwa.core.categories import Categorizer, prepare
from aiwa.core.classifier import ClassificationLoop, Question
from aiwa.core.collector import Collector
from aiwa.core.events import Category, Finding, Level, Segment
from aiwa.core.focus import moment
from aiwa.core.sampling import SamplingSchedule
from aiwa.core.scoreboard import ScoreKeeper
from aiwa.core.session import Action, BelowThreshold, FocusSession
from aiwa.core.openjev import Openjev
from aiwa.core.policy import NudgePolicy
from aiwa.core.rules import default_rules
from aiwa.core.store import Store
from aiwa.services.activitywatch import ActivityWatchSupervisor, find_commands, server_check
from aiwa.ui.board import scoreboard_lines
from aiwa.ui.inbox import Inbox
from aiwa.ui.popup import Popup
from aiwa.ui.sound import Alarm
from aiwa.ui.tray import Tray

SESSION_FOCUS_WINDOW = timedelta(minutes=2)  # short, so a dip in focus is noticed quickly
FAST_POLL_MS = 2_000  # how often to look at what's in focus right now (cheap: latest events only)
RATING_OPTIONS = [(c.value.capitalize(), c.value) for c in Category] + [("Ask later", "later")]
FOCUS_OPTIONS = [("1 scattered", "1"), ("2", "2"), ("3", "3"), ("4", "4"), ("5 deeply focused", "5"), ("Skip", "skip")]
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
        self.sampling = SamplingSchedule(config.sampling) if config.sampling_enabled else None
        self.recent: list[Segment] = []  # latest analyzed timeline, for rating snapshots
        self.scores = ScoreKeeper(
            self.store,
            load=lambda start, end: prepare(self.collector.between(start, end), config, self.categorizer),
            params=config.focus,
            goal_minutes=config.daily_goal_minutes,
            day_starts=config.day_starts,
        )
        self.low_focus = BelowThreshold(config.low_focus_below)
        self.alarm = Alarm(config.alarm_sound, config.alarm_volume)
        self.session: FocusSession | None = None
        self.session_id: int | None = None
        running = self.store.running_session()  # resume a session that was running when aiwa stopped
        if running:
            self.session_id, started = running
            self.session = FocusSession(started, config.session)
        self.tray = Tray(
            on_session=self.toggle_session,
            on_rate=lambda: self.ask_focus("manual"),
            on_inbox=self.open_inbox,
            on_snooze=self.snooze_hour,
            on_settings=lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(CONFIG_PATH))),
            on_autostart=set_autostart,
            autostart_enabled=platforms.current().autostart_installed(),
            on_quit=QApplication.quit,
        )
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
        self.recent = segments
        away = bool(segments) and max(segments, key=lambda s: s.end).away
        self.tray.set_status("away" if away else self.status(segments, now))
        for finding in self.analyzer.run(segments, now):
            if self.policy.allow(finding, now, away=away):
                self.policy.record(finding, now)
                self.show(finding, self.store.log_nudge(finding, now))
        self.update_scoreboard(now)
        self.step_session(segments, now)

    # --- focus sessions --------------------------------------------------------

    def toggle_session(self) -> None:
        now = datetime.now(timezone.utc)
        if self.session:
            self.stop_session(now)
        else:
            self.session_id = self.store.start_session(now)
            self.session = FocusSession(now, self.config.session)
            self.tray.set_session(0)

    def stop_session(self, now: datetime) -> None:
        if not self.session:
            return
        counts = {action.value: n for action, n in self.session.counts.items()}
        self.store.end_session(self.session_id, now, counts)
        self.session = self.session_id = None
        self.alarm.stop()
        self.tray.set_session(None)
        if self.popup.isVisible():
            self.popup.hide()

    def step_session(self, segments: list[Segment], now: datetime) -> None:
        if not self.session:
            return
        minutes = int(self.session.elapsed(now).total_seconds() // 60)
        self.tray.set_session(minutes)
        latest = max(segments, key=lambda s: s.end) if segments else None
        away_since = latest.start if latest and latest.away else None
        short = moment(segments, now, SESSION_FOCUS_WINDOW, self.config.focus)
        low = self.low_focus(short.intensity)
        if away_since is None and not low and self.alarm.ringing:
            self.alarm.stop()  # the user is back, and focused
        action = self.session.step(now, low, away_since)
        if action is Action.NONE:
            return
        if action is Action.ALARM:
            self.alarm.start()  # loops until the user is back or answers
            away = int((now - away_since).total_seconds() // 60)
            message = f"You've been away for {away} min, and your focus session is still running."
            options = [("I'm back", "ok"), ("Stop session", "stop")]
        elif action is Action.WRAP_UP:
            message = f"{minutes} minutes of focus. Time to wrap up and take a real break."
            options = [("Stop session", "stop"), ("Almost done", "ok")]
        elif action is Action.ASK_DONE:
            message = "Your focus has dropped. Is this session done?"
            options = [("Yes, stop", "stop"), ("No, keep going", "ok")]
        else:
            if self.config.sound_on_low_focus:
                self.alarm.start()  # rings until focus is back or the popup is answered
            message = "Your focus is slipping. Come back to what you were working on?"
            options = [("Back on it", "ok"), ("Stop session", "stop")]
        # session messages take priority over any other open question
        self.popup.ask(message, self.on_session_answer, options)

    def on_session_answer(self, response: str) -> None:
        self.alarm.stop()
        if response == "stop":
            self.stop_session(datetime.now(timezone.utc))

    def update_scoreboard(self, now: datetime) -> None:
        try:
            self.scores.update(now)  # the first run fills in today so far
        except (OSError, RuntimeError):
            return
        today = self.scores.today(now)
        self.tray.set_scoreboard(scoreboard_lines(today, self.config.focus.deep_threshold), today.goal_progress)

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
        elif self.sampling and not self.popup.isVisible():
            away = current is None or current.away
            if self.sampling.due(now, away):
                self.ask_focus("sampled")

    def ask_focus(self, source: str) -> None:
        """Ask for a 1–5 focus rating: ground truth for calibrating the focus score."""
        asked_at = datetime.now(timezone.utc)
        self.popup.ask(
            "How focused are you right now?",
            lambda r: self.on_focus_rating(asked_at, r, source),
            FOCUS_OPTIONS,
        )

    def on_focus_rating(self, asked_at: datetime, response: str, source: str) -> None:
        now = datetime.now(timezone.utc)
        snapshot = {}
        for horizon in self.config.focus.horizons:
            m = moment(self.recent, now, horizon, self.config.focus)
            snapshot[f"{int(horizon.total_seconds() // 60)}m"] = {
                "intensity": m.intensity, "depth": m.depth, "fit": m.fit,
                "hit_rate": m.hit_rate, "continuity": m.continuity,
            }
        rating = None if response == "skip" else int(response)
        self.store.add_rating(asked_at, now, rating, source, snapshot)

    def status(self, segments: list[Segment], now: datetime) -> str:
        horizon = self.config.focus.main_horizon
        focus = moment(segments, now, horizon, self.config.focus)
        if focus.intensity is None:
            return f"focus now – (mostly away, last {_minutes(horizon)})"
        return f"focus now {focus.intensity:.2f} (last {_minutes(horizon)})"

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


def set_autostart(enabled: bool) -> None:
    os_support = platforms.current()
    if enabled:
        os_support.install_autostart([sys.executable, "-m", "aiwa"])
    else:
        os_support.uninstall_autostart()


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
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(DATA_DIR / "aiwa.lock"))  # released automatically if aiwa crashes
    if not lock.tryLock(0):
        print("aiwa is already running.", flush=True)
        return 0
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

