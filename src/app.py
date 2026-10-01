"""The running daemon: a tray app that polls, analyzes and nudges."""

from __future__ import annotations

import signal
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta, timezone

from platformdirs import user_log_path
from PySide6.QtCore import QLockFile, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication

from aiwa import platforms
from aiwa.config import CONFIG_PATH, DATA_DIR, DB_PATH, UNTRACKED, Config
from aiwa.core.analyzer import Analyzer
from aiwa.core.categories import Categorizer, prepare
from aiwa.core.classifier import ClassificationLoop, Question
from aiwa.core.collector import Collector
from aiwa.core.events import Category, Finding, Level, Segment
from aiwa.signals.focus import moment
from aiwa.core.sampling import SamplingSchedule
from aiwa.metrics.keeper import ScoreKeeper
from aiwa.metrics.day import day_bounds, summarize_day
from aiwa.core.openjev import Openjev, assess_task, classify_activity, is_todo, still_there, suggest_group, suggest_kind
from aiwa.core import kinds
from aiwa.metrics.quota import QuotaKeeper
from aiwa.core.policy import NudgePolicy
from aiwa.rules import default_rules
from aiwa.core.rhythm import Rhythm
from aiwa.core.store import Store
from aiwa.flows.bedtime import BedtimeFlow
from aiwa.flows.capture import CaptureFlow
from aiwa.flows.meditation import MeditationFlow
from aiwa.flows.reminders import RemindersFlow
from aiwa.flows.experiment import ExperimentFlow, experiment_lines
from aiwa.flows.grand import GrandFlow
from aiwa.flows.sprint import SprintFlow
from aiwa.signals.base import Values
from aiwa.flows.base import Flow, FlowContext
from aiwa.flows.session import NO_DATA_AFTER, SessionFlow
from aiwa.flows.budget import BudgetFlow
from aiwa.flows.hub import HubFlow
from aiwa.flows.suggest import SuggestSessionFlow
from aiwa.signals.defaults import default_signals
from aiwa.core.craftsman import WorthAsking, pick, site_weeks
from aiwa.core.association import AssociationParams, contributions, pair_minutes
from aiwa.ui.background import Background
from aiwa.flows.craftsman import CraftsmanFlow, verdict_lines
from aiwa.flows.shutdown import ShutdownFlow
from aiwa.core.backlog import minutes_text
from aiwa.core.budget import shallow_share
from aiwa.metrics.consistency import ConsistencyParams, consistency
from aiwa.core.shutdown import workday
from aiwa.core.weekly import WeekFacts, review_due, review_text, week_start
from aiwa.flows.morning import MorningFlow
from aiwa.flows.routines import RoutinesFlow
from aiwa.flows.rhythm import RhythmFlow
from aiwa.flows.tasks import TasksFlow
from aiwa.services.activitywatch import ActivityWatchSupervisor, find_commands, server_check
from aiwa.ui.board import budget_lines, consistency_lines, rhythm_lines, scoreboard_lines, sleep_lines, task_lines
from aiwa.ui.popup import Popup
from aiwa.ui.sound import Alarm
from aiwa.ui.tray import Tray

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
        self.assess = (lambda task: assess_task(openjev, task)) if openjev else None  # deep/shallow, size, vague?
        self.suggest_group = self.make_group_suggester(openjev)
        self.helper = make_helper(config)  # the AI's step suggestions, or None
        self.classifier = ClassificationLoop(
            config,
            self.store,
            suggest=(lambda activity: suggest_kind(openjev, activity)) if openjev else None,
            executor=ThreadPoolExecutor(max_workers=2) if openjev else None,  # never block the UI on the network
        )
        self.classifier.backfill_kinds()  # sites classified before kinds existed: their kind, quietly
        self.analyzer = Analyzer(default_rules())
        self.policy = NudgePolicy(timedelta(minutes=config.min_minutes_between_nudges))
        self.sampling = SamplingSchedule(config.sampling) if config.sampling_enabled else None
        self.recent: list[Segment] = []  # latest analyzed timeline, for rating snapshots
        self.scores = ScoreKeeper(
            self.store,
            load=lambda start, end: prepare(self.collector.between(start, end), config, self.categorizer),
            params=config.focus,
            day_starts=config.day_starts,
        )
        self.quota = QuotaKeeper(self.store, config.quota, config.day_starts, config.focus.deep_threshold)
        self.session_flow = SessionFlow(self)  # before the tray: its menu starts and stops sessions
        self.rhythm = Rhythm(self.store, config.rhythm, config.day_starts, config.focus.deep_threshold)
        self.tray = Tray(
            on_session=self.session_flow.toggle_session,
            on_tasks=lambda: self.tasks.open_board(),
            on_new_task=lambda: self.tasks.new_task(),
            on_task_done=lambda: self.tasks.task_done(),
            on_walk=lambda: self.meditation.start(),
            on_grand=lambda: self.grand_prompts.start(),
            on_experiment=lambda: self.experiments.start(),
            on_sprint=lambda: self.sprint_prompts.start(),
            on_rate=lambda: self.ask_focus("manual"),
            on_snooze=self.snooze_hour,
            on_settings=lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(CONFIG_PATH))),
            on_autostart=set_autostart,
            autostart_enabled=platforms.current().autostart_installed(),
            on_quit=QApplication.quit,
        )
        self.popup = Popup()
        self.tasks = TasksFlow(
            self.store, self.popup, today=self.rhythm.today, day_starts=config.day_starts,
            deep_minutes_today=lambda now: self.scores.today(now).deep_minutes,
            assess=self.assess, suggest_group=self.suggest_group, helper=self.helper,
        )
        self.bedtime = BedtimeFlow(
            self.store, config.bedtime, config.day_starts, self.popup,
            # its own player: the session logic stops its alarm when focus is fine, which must not end this one
            alarm=Alarm(config.alarm_sound, config.alarm_volume),
            lock_screen=platforms.current().lock_screen, today=self.rhythm.today,
        )
        self.morning = MorningFlow(
            self.store, self.popup, alarm=Alarm(config.alarm_sound, config.alarm_volume), today=self.rhythm.today,
            first_activity=lambda now: self.bedtime.last_night(now)[1],
            todays_work=self.todays_work,
            request_session=lambda: self.tasks.request_session(self.session_flow.start_session),
        )
        self.routines = RoutinesFlow(self.store, self.popup, config.bedtime.wind_down, config.day_starts,
                                       always_ask=config.routines_always_ask,
                                       classify=(lambda text: classify_activity(openjev, text)) if openjev else None,
                                       still_there=(lambda context: still_there(openjev, context)) if openjev else None,
                                       still_there_above=config.routines_skip_if_still_there)
        self.capture = CaptureFlow(self.store, self.popup, self.tasks,
                                      (lambda note: is_todo(openjev, note)) if openjev else None)
        self.reminder_prompts = RemindersFlow(self.store, self.popup, config.day_starts)
        self.experiments = ExperimentFlow(self.store, self.popup, self.rhythm.today, self.distraction_candidates)
        self.grand_prompts = GrandFlow(self.store, self.popup, self.session_flow.start_grand,
                                          next_task=lambda: self.tasks.next_task(datetime.now(timezone.utc))[1])
        self.sprint_prompts = SprintFlow(self.popup, self.session_flow.start_sprint,
                                            next_task=lambda: self.tasks.next_task(datetime.now(timezone.utc))[1],
                                            new_task=lambda: self.tasks.new_task())
        self.signals = default_signals(config.focus)

        self.craftsman = CraftsmanFlow(self.store, self.popup, start_test=lambda key: self.experiments.start_for(key))
        self.worth_asking = WorthAsking()
        self._week_sites: tuple[datetime, dict] | None = None
        self._computing = False
        self.background = Background()
        self.meditation = MeditationFlow(self.store, self.popup, self.session_flow.start_walk,
                                            current_task=lambda: self.tasks.next_task(datetime.now(timezone.utc))[1])
        self.shutdown = ShutdownFlow(self.store, self.popup, self.tasks, config.shutdown, config.day_starts,
                                        self.shutdown_wrap_up, alarm=Alarm(config.alarm_sound, config.alarm_volume),
                                        weekly_review=self.weekly_review, save_review=self.save_weekly_review,
                                        tools_check=self.tools_check)
        self.prompts = RhythmFlow(
            self.store, self.rhythm, config.rhythm, config.day_starts, self.popup,
            request_session=lambda: self.tasks.request_session(self.session_flow.start_session),
            ask_anything_new=self.tasks.ask_anything_new,
        )
        request_session = lambda: self.tasks.request_session(self.session_flow.start_session)
        self.budget_flow = BudgetFlow(self.popup, config.shallow, config.shutdown, self.rhythm.today,
                                      self.shallow_today, request_session)
        self.suggest_flow = SuggestSessionFlow(self.popup, request_session)
        self.hub_flow = HubFlow(self.popup, self.session_flow.on_session_answer)
        # the order flows run in, each tick / poll (earlier ones get the popup first)
        self.flows: list[Flow] = [
            self.session_flow, self.bedtime, self.morning, self.routines, self.reminder_prompts, self.experiments, self.budget_flow,
            self.capture, self.suggest_flow, self.shutdown, self.prompts, self.hub_flow,
        ]
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(config.poll_seconds * 1000)
        self.fast_timer = QTimer()
        self.fast_timer.timeout.connect(self.poll)
        self.fast_timer.start(FAST_POLL_MS)

    def make_group_suggester(self, openjev):
        """An existing group that fits (openjev), else a name for a new one (the AI)."""
        helper = make_helper(self.config)
        if openjev is None and helper is None:
            return None

        def suggest(task: str, groups: list[str]) -> str | None:
            existing = suggest_group(openjev, task, groups) if openjev else None
            return existing or (helper.group_name(task, "") if helper else None)

        return suggest

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
        latest = max(segments, key=lambda s: s.end) if segments else None
        active = latest is not None and not latest.away and now - latest.end <= NO_DATA_AFTER
        self.update_scoreboard(now)
        self.week_sites(now)  # keeps the craftsman data fresh (hourly, in the background)
        ctx = FlowContext(now, segments, latest, self.state(now), active=active, in_session=self.session_flow.session is not None,
                          away_since=latest.start if latest is not None and latest.away else None)
        ctx.values = Values(self.signals, ctx)
        for flow in self.flows:
            flow.tick(ctx)

    # --- focus sessions --------------------------------------------------------

    def todays_work(self, now: datetime) -> str:
        """One line for the morning: the most urgent goal and its next task, and the deep-work goal."""
        group, task = self.tasks.next_task(now)
        quota = self.quota.today(now, self.scores.today(now).deep_minutes)
        goal = f"Today's deep-work goal: {minutes_text(quota)}."
        if task is None:
            return f"{goal} Your task list is empty: add what needs doing."
        where = f"{group.name}: " if group else ""
        return f"{goal} First up: {where}{task.title} (~{minutes_text(task.estimate)})."

    def shutdown_wrap_up(self, now: datetime) -> str:
        """The shutdown's last step: today's deep work, and where tomorrow starts."""
        deep = self.scores.today(now).deep_minutes
        quota = self.quota.today(now, deep)
        lines = [f"Deep work today: {minutes_text(deep)} of {minutes_text(quota)}."]
        tz = now.astimezone().tzinfo
        today = self.rhythm.today(now)
        for ahead in range(1, 8):
            block = self.rhythm.block(today + timedelta(days=ahead), tz)
            if block is not None:
                when = "Tomorrow" if ahead == 1 else f"{block.start.astimezone():%A}"
                lines.append(f"{when}: deep-work block at {block.start.astimezone():%H:%M}.")
                break
        group, task = self.tasks.next_task(now)
        if task is not None:
            lines.append(f"First up: {task.title} (~{minutes_text(task.estimate)}).")
        lines.append("Everything is written down. The workday is over.")
        return "\n".join(lines)

    def weekly_review(self, now: datetime) -> str | None:
        """The week's facts, when the weekly review is due (core/weekly.py); else None."""
        today = self.rhythm.today(now)
        last = self.store.last_weekly_review()
        if not review_due(today, last[0] if last else None, self.config.shutdown.days):
            return None
        monday = week_start(today)
        deep_by_day, shallow, active = {}, 0, 0
        for back in range((today - monday).days + 1):
            day = monday + timedelta(days=back)
            _, start, end = day_bounds(datetime.combine(day, time(12)).astimezone(), self.config.day_starts)
            summary = summarize_day(day, self.store.minutes(start, end), self.config.focus.deep_threshold, 0)
            deep_by_day[day] = summary.deep_minutes
            if workday(day, self.config.shutdown):
                share = shallow_share(summary.minutes_by_activity)
                shallow, active = shallow + share.shallow, active + share.active
        _, week_from, _ = day_bounds(datetime.combine(monday, time(12)).astimezone(), self.config.day_starts)
        groups = {g.id: g for g in self.store.groups()}
        minutes: dict[int, int] = {}
        for session in self.rhythm.sessions(week_from, now, now):
            if session.group_id in groups:
                minutes[session.group_id] = minutes.get(session.group_id, 0) + session.deep_minutes
        worked_on = {t.group_id for t in self.store.tasks() if t.group_id is not None}  # groups with open tasks
        by_group = sorted(
            ((g.name, g.priority, minutes.get(g.id, 0)) for g in groups.values() if g.id in minutes or g.id in worked_on),
            key=lambda row: -row[2],
        )
        return review_text(WeekFacts(
            deep_by_day=deep_by_day, daily_goal=self.quota.base(now), by_group=by_group,
            chain=self.rhythm.chain(now), consistency=consistency_lines(self.consistency(now))[0],
            last_answer=last[1] if last else None, workdays=self.config.shutdown.days,
            shallow=(shallow, active), shallow_limit=self.config.shallow.limit,
            top_deep=self.usage(Category.DEEP, week_from, now),  # the vital few
            tools=verdict_lines(self.week_sites(now), self.store.verdicts(), {g.id: g.name for g in self.store.groups()}),
        ))

    def week_sites(self, now: datetime) -> dict:
        """This week's sites/apps with the goals they serve (craftsman check); refreshed hourly in
        the background, since four weeks of history take a few seconds to read. Empty until ready."""
        if (self._week_sites is None or now - self._week_sites[0] >= timedelta(hours=1)) and not self._computing:
            self._computing = True
            self.background.run(lambda: self.compute_week_sites(now), self._week_sites_ready)
        return self._week_sites[1] if self._week_sites else {}

    def _week_sites_ready(self, result) -> None:
        self._computing = False
        if result is not None:
            self._week_sites = result

    def compute_week_sites(self, now: datetime) -> tuple[datetime, dict]:
        """(runs in a worker thread) Pairs (goal, window) over the lookback → what serves which goal;
        then this week's sites (core/association.py, core/craftsman.py)."""
        store = Store(DB_PATH)  # its own connection: SQLite connections stay in their thread
        params = AssociationParams()
        since = now - params.lookback
        categorizer = Categorizer(self.config.categories, store)
        segments = [s for s in prepare(self.collector.between(since, now), self.config, categorizer)
                    if s.app != UNTRACKED]
        sessions = [(a, b or now, g) for a, b, _, _, g in store.sessions_between(since, now)]
        contributes = contributions(pair_minutes(segments, sessions), params)
        for key, (verdict, group, _) in store.verdicts().items():
            if verdict == "serves" and group is not None:  # the user's answer wins
                contributes.setdefault(key, set()).add(group)
        today = self.rhythm.today(now)
        _, week_from, _ = day_bounds(datetime.combine(week_start(today), time(12)).astimezone(), self.config.day_starts)
        notes = [(Segment(now, now, app or "", url=url).key, became_task)
                 for url, app, became_task in store.note_sources(week_from) if url or app]
        week = [s for s in segments if s.end > week_from]
        return now, site_weeks(week, contributes, notes)

    def tools_check(self, now: datetime) -> None:
        """The craftsman question: one site per weekly review, picked by the rule."""
        site = pick(self.week_sites(now), set(self.store.verdicts()), self.worth_asking)
        if site is not None:
            self.craftsman.ask(site, self.store.groups())

    def save_weekly_review(self, now: datetime, answer: str | None) -> None:
        self.store.add_weekly_review(week_start(self.rhythm.today(now)), now, answer)

    def usage(self, category: Category, since: datetime, now: datetime) -> list[tuple[str, int]]:
        """Sites/apps of a category with their minutes since `since`, most first."""
        try:
            segments = prepare(self.collector.between(since, now), self.config, self.categorizer)
        except OSError:
            return []
        minutes: dict[str, float] = {}
        for s in segments:
            if not s.away and s.category is category and s.app != UNTRACKED:
                minutes[s.key] = minutes.get(s.key, 0) + s.duration.total_seconds() / 60
        return sorted(((k, int(m)) for k, m in minutes.items() if m >= 1), key=lambda km: -km[1])

    def distraction_candidates(self) -> list[tuple[str, int]]:
        """Distraction sites/apps with minutes in the last week, most first (for the 30-day test)."""
        now = datetime.now(timezone.utc)
        return self.usage(Category.DISTRACTION, now - timedelta(days=7), now)

    def state(self, now: datetime) -> dict:
        """The app's own values, for signals and flows."""
        return {
            "in_session": self.session_flow.session is not None,
            "shutdown_done": self.shutdown.done_today(now),
            "popup_open": self.popup.isVisible(),
            "minutes_since_suggested": self.suggest_flow.minutes_since_suggested(now),
        }

    def shallow_today(self, now: datetime):
        return shallow_share(self.scores.today(now).minutes_by_activity)

    def update_scoreboard(self, now: datetime) -> None:
        try:
            self.scores.update(now)  # the first run fills in today so far
        except (OSError, RuntimeError):
            return
        deep = self.scores.today(now).deep_minutes
        today = self.scores.today(now, self.quota.today(now, deep))
        _, day_start, day_end = day_bounds(now, self.config.day_starts)
        group, task = self.tasks.next_task(now)
        shallow = shallow_share(today.minutes_by_activity)
        lines = (
            scoreboard_lines(today, self.config.focus.deep_threshold)
            + budget_lines(shallow, self.config.shallow.limit)
            + rhythm_lines(self.prompts.todays_block(now), now, self.rhythm.chain(now), self.rhythm.todays_sessions(now))
            + consistency_lines(self.consistency(now))
            + experiment_lines(self.store.experiments(("running",)), self.rhythm.today(now))
            + task_lines(group, task, self.store.tasks_done_between(day_start, day_end))
            + sleep_lines(*self.bedtime.last_night(now))
        )
        self.tray.set_scoreboard(lines, today.goal_progress)

    def consistency(self, now: datetime):
        params = ConsistencyParams()
        starts = self.rhythm.first_starts(now, params.history_days)
        return consistency(starts, self.rhythm.today(now), self.config.day_starts, params)

    def poll(self) -> None:
        """Every few seconds: classify what's in focus, asking the user if needed."""
        now = datetime.now(timezone.utc)
        try:
            current = self.collector.current()
        except OSError:
            return  # ActivityWatch not reachable; tick() reports it in the tray
        question = self.classifier.observe(current, now)
        present = current is not None and not current.away
        ctx = FlowContext(now, state=self.state(now), latest=current, current=current, active=present,
                          in_session=self.session_flow.session is not None,
                          category=self.categorizer.categorize(current) if present else None,
                          kind=self.categorizer.kind(current) if present else None)
        for flow in self.flows:
            flow.poll(ctx)
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
            kind = self.store.get_kind(question.key)
            what = f"looks like {kinds.label(kind[0])}" if kind else "was classified by openjev"
            message = (f"“{question.key}” {what} ({guess.confidence or 0:.0%} sure), "
                       f"so it counts as {guess.category.value}. Right?")
            options = [("Right", "ok"), ("Other kind…", "_kinds"), ("Counts as…", "_counts"), ("Ask later", "later")]
        else:
            kind = self.store.get_kind(question.key)
            message = f"What is “{question.key}”?"
            if kind and kind[0] != "other":
                message += f"\n(openjev guesses {kinds.label(kind[0])}, {kind[2] or 0:.0%} sure)"
            options = [(group, f"_group:{group}") for group in kinds.GROUPS] + [("Ask later", "later")]
        self.popup.ask(message, lambda r: self.on_classify_answer(question, r), options)

    def on_classify_answer(self, question: Question, response: str) -> None:
        """Answers to classification popups; some open a follow-up (kind groups, categories)."""
        key = question.key
        if response == "_kinds":
            self.popup.ask(f"What is “{key}”?", lambda r: self.on_classify_answer(question, r),
                           [(group, f"_group:{group}") for group in kinds.GROUPS])
        elif response.startswith("_group:"):
            group = response.removeprefix("_group:")
            self.popup.ask(f"What is “{key}”? ({group})", lambda r: self.on_classify_answer(question, r),
                           [(k.label, f"kind:{k.key}") for k in kinds.in_group(group)])
        elif response == "_counts":
            self.popup.ask(f"How does “{key}” count for you? (only this one)",
                           lambda r: self.on_classify_answer(question, r), RATING_OPTIONS[:-1])
        else:
            self.classifier.answered(question, response, datetime.now(timezone.utc))
            if response.startswith("kind:") and kinds.default_category(response.removeprefix("kind:")) is None:
                self.on_classify_answer(question, "_counts")  # "something else": how does it count?

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

    def snooze_hour(self) -> None:
        self.policy.snooze(datetime.now(timezone.utc) + timedelta(hours=1))
        self.tray.set_status("snoozed for 1 hour")


def make_helper(config: Config):
    """The AI's step suggestions (Gemini), if enabled and a key is set; otherwise None."""
    if not (config.ai_enabled and config.gemini_api_key):
        return None
    from aiwa.core.ai import TaskHelper

    return TaskHelper(config.gemini_api_key, config.ai)


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
    commands = find_commands(os_support.ACTIVITYWATCH_DIRS, os_support.EXECUTABLE_SUFFIX, config.aw_modules,
                             config.aw_optional_modules)
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
    app.setQuitOnLastWindowClosed(False)  # closing a window must not quit the daemon
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

