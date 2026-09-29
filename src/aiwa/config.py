"""User settings, loaded from a TOML file in the OS config directory."""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from datetime import time, timedelta
from pathlib import Path

from platformdirs import user_config_path, user_data_path

from aiwa.core.ai import AISettings
from aiwa.core.bedtime import BedtimeParams
from aiwa.core.budget import BudgetParams
from aiwa.core.events import Category
from aiwa.core.focus.params import FocusParams
from aiwa.core.quota import QuotaParams
from aiwa.core.sampling import SamplingParams
from aiwa.core.schedule import RhythmParams
from aiwa.core.session import SessionParams
from aiwa.core.shutdown import ShutdownParams

CONFIG_PATH = user_config_path("aiwa") / "config.toml"
DATA_DIR = user_data_path("aiwa")
DB_PATH = DATA_DIR / "aiwa.db"

DEFAULT_CONFIG = """\
# aiwa settings

[activitywatch]
host = "127.0.0.1"
port = 5600
# Let aiwa start ActivityWatch's server and watchers itself, so ActivityWatch's
# own tray icon isn't needed. If ActivityWatch is already running, aiwa leaves it alone.
manage = true
modules = ["aw-server", "aw-watcher-afk", "aw-watcher-window"]

[analysis]
poll_seconds = 15      # how often to re-analyze recent activity (tray status, focus, nudges)
lookback_minutes = 30  # how much recent history each check looks at

[nudges]
min_minutes_between = 20  # never interrupt more often than this

[focus]
# Focus intensity = depth × stability × continuity. See docs/components.md.
horizons_minutes = [2, 5, 30]   # sliding-window sizes; the middle one is the main score (deep minutes)
shallow_weight = 0.3            # depth: how much shallow time counts (deep 1, distraction 0)
capacity = 5                    # stability: items a focused working set can hold
dwell_scale_seconds = 20        # continuity: mean time per item that scores 0.63
deep_threshold = 0.6            # a minute counts as deep work at this intensity or above

[scoreboard]
# The daily deep-work quota (the ring on the tray icon). Pass 80% of today's quota and it
# rises by one step for today; pass 80% of the base 3 days in a row and the base rises.
quota_start_minutes = 240    # 4 h
quota_step_minutes = 60
quota_max_minutes = 600      # 10 h
day_starts = "04:00"     # when "today" begins; work after midnight counts toward the day before

[ai]
# The AI helper (Google Gemini; key: GEMINI_API_KEY in .env): suggests steps when a task
# needs breaking down. Models are tried in order when one is busy. Without it, or when
# none answers in time, you write the steps yourself.
enabled = true
model = "gemini-3.5-flash"
fallback_models = ["gemini-3.5-flash-lite"]
timeout_seconds = 20

[rhythm]
# A deep-work block at the same time every day (Deep Work's "rhythmic" style).
# Each evening aiwa asks whether anything new needs taking care of.
days = ["mon", "tue", "wed", "thu", "fri"]
start = "09:00"
minutes = 90
planning_time = "21:30"      # when to ask "anything new to take care of?"
kept_deep_minutes = 25       # a block is kept (chain +1) with this much deep work in a session in it

[routines]
# After an absence aiwa sometimes asks what it was (more often for longer ones).
always_ask = false   # true: ask about every absence of 5+ minutes (for trying it out)

[shutdown]
# The end of the workday (Deep Work's shutdown ritual): go through today's notes, write
# down anything still on your mind, look at tomorrow, then "shutdown complete". After
# that aiwa stops asking about work for the day.
enabled = true
time = "18:00"
days = ["mon", "tue", "wed", "thu", "fri"]

[shallow]
# The shallow-work budget: the share of your time at the computer that may go to shallow
# work (email, chat, admin) on workdays. A soft limit: at the limit there's a 50% chance
# aiwa mentions it per check (every 30 minutes, outside sessions), more above, less below.
limit = 0.30
softness = 0.05   # how gradual: 25% → 27% chance, 35% → 73%, 40% → 88%

[bedtime]
# An anchor for sleep, every night: from wind_down a reminder every 5 minutes while you're
# active ("10 more minutes" once per night); from hard_stop the alarm rings while you're
# active, until you lock the screen, the Mac sleeps or you step away.
enabled = true
wind_down = "22:00"
hard_stop = "00:00"
alarm = true

[session]
# Focus sessions are started and stopped from the tray; they have no fixed length.
build_up_minutes = 25       # before this, a dip in focus gets a poke every minute
wrap_up_minutes = 50        # after this, "time to wrap up" every 2 minutes until you stop
low_focus_below = 0.35      # "low focus": 2-minute focus score below this (and not rising)
away_alarm_minutes = 5      # away this long during a session → alarm, looping until you're back
away_end_minutes = 10       # away this long → the session ends, as of when you left
alarm_sound = ""            # path to a sound file (mp3/wav); empty = the built-in alarm clock
alarm_volume = 1.0          # 0.0 – 1.0
sound_on_low_focus = true   # ring the alarm while focus is slipping, until it's back

[sampling]
# A few times a day aiwa asks "how focused are you right now? (1–5)" at random
# moments, to calibrate the focus score to you.
enabled = true
per_day = 5
start = "09:00"
end = "18:00"
min_gap_minutes = 45

[classification]
suggest_after_seconds = 2    # ask openjev about an unclassified app/website after this long on it
ask_after_seconds = 10       # ask you, if still unclassified or openjev is unsure, after this long
ask_track_after_seconds = 5  # ask whether to track an untracked app after using it this long
ignore_apps = []             # apps never to ask about, on top of the OS's own system windows

[openjev]
# Optional: classify new apps/websites automatically before asking you. Only the
# app name or website domain is sent. The API key is read from OPENJEV_API_KEY
# (environment or a .env file next to this config) unless set here.
enabled = false
min_confidence = 0.7  # below this, you are still asked (openjev's guess is shown)
# api_key = ""

# Only apps/windows matching a rule below are recorded by name.
# Everything else is seen only as "(untracked)", so switches still count
# but no names, titles or URLs are kept. `title` and `url` are optional
# regular expressions.
[[track]]
app = "Code"

[[track]]
app = "Google Chrome"

[[track]]
app = "Slack"

# How activities count in Deep Work terms: deep, shallow, distraction, neutral.
# Rules are checked in order; the first match wins. Anything not matched is
# asked about once and remembered.
[[category]]
app = "Code"
category = "deep"

[[category]]
app = "Slack"
category = "shallow"

[[category]]
app = "Google Chrome"
url = "youtube\\\\.com|facebook\\\\.com|instagram\\\\.com|reddit\\\\.com|x\\\\.com"
category = "distraction"
"""

UNTRACKED = "(untracked)"


def _regex(value: str | None) -> re.Pattern[str] | None:
    return re.compile(value, re.IGNORECASE) if value else None


@dataclass(frozen=True)
class Match:
    """Matches an app, optionally narrowed by window title and/or URL."""

    app: str
    title: re.Pattern[str] | None = None
    url: re.Pattern[str] | None = None

    def matches(self, app: str, title: str, url: str | None) -> bool:
        if app != self.app:
            return False
        if self.title and not self.title.search(title):
            return False
        return not self.url or bool(url and self.url.search(url))

    @classmethod
    def parse(cls, raw: dict) -> Match:
        return cls(raw["app"], _regex(raw.get("title")), _regex(raw.get("url")))


@dataclass(frozen=True)
class CategoryRule:
    match: Match
    category: Category


@dataclass
class Config:
    aw_host: str = "127.0.0.1"
    aw_port: int = 5600
    aw_manage: bool = True
    aw_modules: list[str] = field(default_factory=lambda: ["aw-server", "aw-watcher-afk", "aw-watcher-window"])
    poll_seconds: int = 15
    lookback_minutes: int = 30
    min_minutes_between_nudges: int = 20
    suggest_after_seconds: int = 2
    ask_after_seconds: int = 10
    ignore_apps: list[str] = field(default_factory=list)
    ask_track_after_seconds: int = 5
    focus: FocusParams = field(default_factory=FocusParams)
    quota: QuotaParams = field(default_factory=QuotaParams)
    day_starts: time = time(4, 0)
    rhythm: RhythmParams = field(default_factory=RhythmParams)
    bedtime: BedtimeParams = field(default_factory=BedtimeParams)
    shutdown: ShutdownParams = field(default_factory=ShutdownParams)
    shallow: BudgetParams = field(default_factory=BudgetParams)
    routines_always_ask: bool = False
    ai_enabled: bool = True
    ai: AISettings = field(default_factory=AISettings)
    gemini_api_key: str | None = None
    session: SessionParams = field(default_factory=SessionParams)
    low_focus_below: float = 0.35
    alarm_sound: Path | None = None  # None = built-in
    alarm_volume: float = 1.0
    sound_on_low_focus: bool = True
    sampling_enabled: bool = True
    sampling: SamplingParams = field(default_factory=SamplingParams)
    openjev_enabled: bool = False
    openjev_api_key: str | None = None
    openjev_min_confidence: float = 0.7
    track: list[Match] = field(default_factory=list)
    categories: list[CategoryRule] = field(default_factory=list)

    def is_tracked(self, app: str, title: str, url: str | None = None) -> bool:
        return any(rule.matches(app, title, url) for rule in self.track)

    def has_track_rule(self, app: str) -> bool:
        """Whether any rule mentions this app, even one limited to some titles or URLs."""
        return any(rule.app == app for rule in self.track)

    def add_tracked_apps(self, apps: list[str]) -> None:
        """Track these apps too (the ones the user accepted in a popup)."""
        self.track += [Match(app) for app in apps if not self.has_track_rule(app)]


def load(path: Path = CONFIG_PATH) -> Config:
    """Load the config, writing the default file on first run."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    # utf-8-sig: also reads a file saved with a byte-order mark (e.g. by Windows Notepad)
    return parse(tomllib.loads(path.read_text(encoding="utf-8-sig")))


def parse(raw: dict) -> Config:
    aw = raw.get("activitywatch", {})
    analysis = raw.get("analysis", {})
    nudges = raw.get("nudges", {})
    classification = raw.get("classification", {})
    openjev = raw.get("openjev", {})
    focus = raw.get("focus", {})
    return Config(
        aw_host=aw.get("host", "127.0.0.1"),
        aw_port=aw.get("port", 5600),
        aw_manage=aw.get("manage", True),
        aw_modules=aw.get("modules", ["aw-server", "aw-watcher-afk", "aw-watcher-window"]),
        poll_seconds=analysis.get("poll_seconds", 15),
        lookback_minutes=analysis.get("lookback_minutes", 30),
        min_minutes_between_nudges=nudges.get("min_minutes_between", 20),
        suggest_after_seconds=classification.get("suggest_after_seconds", 2),
        ask_after_seconds=classification.get("ask_after_seconds", 10),
        ignore_apps=list(classification.get("ignore_apps", [])),
        ask_track_after_seconds=classification.get("ask_track_after_seconds", 5),
        focus=parse_focus(focus),
        quota=QuotaParams(
            start=raw.get("scoreboard", {}).get("quota_start_minutes", QuotaParams.start),
            step=raw.get("scoreboard", {}).get("quota_step_minutes", QuotaParams.step),
            maximum=raw.get("scoreboard", {}).get("quota_max_minutes", QuotaParams.maximum),
        ),
        day_starts=time.fromisoformat(raw.get("scoreboard", {}).get("day_starts", "04:00")),
        rhythm=parse_rhythm(raw.get("rhythm", {})),
        bedtime=parse_bedtime(raw.get("bedtime", {})),
        shutdown=parse_shutdown(raw.get("shutdown", {})),
        shallow=BudgetParams(limit=raw.get("shallow", {}).get("limit", BudgetParams().limit),
                             softness=raw.get("shallow", {}).get("softness", BudgetParams().softness)),
        routines_always_ask=raw.get("routines", {}).get("always_ask", False),
        ai_enabled=raw.get("ai", {}).get("enabled", True),
        ai=AISettings(
            model=raw.get("ai", {}).get("model", AISettings.model),
            fallback_models=tuple(raw.get("ai", {}).get("fallback_models", AISettings().fallback_models)),
            timeout=raw.get("ai", {}).get("timeout_seconds", AISettings.timeout),
        ),
        gemini_api_key=os.environ.get("GEMINI_API_KEY"),
        session=parse_session(raw.get("session", {})),
        low_focus_below=raw.get("session", {}).get("low_focus_below", 0.35),
        alarm_sound=Path(raw["session"]["alarm_sound"]).expanduser() if raw.get("session", {}).get("alarm_sound") else None,
        alarm_volume=raw.get("session", {}).get("alarm_volume", 1.0),
        sound_on_low_focus=raw.get("session", {}).get("sound_on_low_focus", True),
        sampling_enabled=raw.get("sampling", {}).get("enabled", True),
        sampling=parse_sampling(raw.get("sampling", {})),
        openjev_enabled=openjev.get("enabled", False),
        openjev_api_key=openjev.get("api_key") or os.environ.get("OPENJEV_API_KEY"),
        openjev_min_confidence=openjev.get("min_confidence", 0.7),
        track=[Match.parse(t) for t in raw.get("track", [])],
        categories=[
            CategoryRule(Match.parse(c), Category(c["category"]))
            for c in raw.get("category", [])
        ],
    )


def parse_bedtime(raw: dict) -> BedtimeParams:
    d = BedtimeParams()
    return BedtimeParams(
        enabled=raw.get("enabled", d.enabled),
        wind_down=time.fromisoformat(raw["wind_down"]) if "wind_down" in raw else d.wind_down,
        hard_stop=time.fromisoformat(raw["hard_stop"]) if "hard_stop" in raw else d.hard_stop,
        alarm=raw.get("alarm", d.alarm),
    )


def parse_shutdown(raw: dict) -> ShutdownParams:
    d = ShutdownParams()
    return ShutdownParams(
        enabled=raw.get("enabled", d.enabled),
        time=time.fromisoformat(raw["time"]) if "time" in raw else d.time,
        days=tuple(day.lower()[:3] for day in raw.get("days", d.days)),
    )


def parse_rhythm(raw: dict) -> RhythmParams:
    d = RhythmParams()
    clock = lambda key, default: time.fromisoformat(raw[key]) if key in raw else default
    return RhythmParams(
        days=tuple(day.lower()[:3] for day in raw.get("days", d.days)),
        start=clock("start", d.start),
        minutes=raw.get("minutes", d.minutes),
        planning_time=clock("planning_time", d.planning_time),
        kept_deep_minutes=raw.get("kept_deep_minutes", d.kept_deep_minutes),
    )


def parse_session(raw: dict) -> SessionParams:
    d = SessionParams()
    minutes = lambda key, default: timedelta(minutes=raw.get(key, default.total_seconds() / 60))
    return SessionParams(
        build_up=minutes("build_up_minutes", d.build_up),
        wrap_up=minutes("wrap_up_minutes", d.wrap_up),
        away_alarm_after=minutes("away_alarm_minutes", d.away_alarm_after),
        away_end_after=minutes("away_end_minutes", d.away_end_after),
    )


def parse_sampling(raw: dict) -> SamplingParams:
    defaults = SamplingParams()
    return SamplingParams(
        per_day=raw.get("per_day", defaults.per_day),
        start=time.fromisoformat(raw["start"]) if "start" in raw else defaults.start,
        end=time.fromisoformat(raw["end"]) if "end" in raw else defaults.end,
        min_gap=timedelta(minutes=raw.get("min_gap_minutes", defaults.min_gap.total_seconds() / 60)),
    )


def parse_focus(raw: dict) -> FocusParams:
    defaults = FocusParams()
    weights = dict(defaults.weights)
    weights[Category.SHALLOW] = raw.get("shallow_weight", weights[Category.SHALLOW])
    return FocusParams(
        weights=weights,
        capacity=raw.get("capacity", defaults.capacity),
        dwell_scale=timedelta(seconds=raw.get("dwell_scale_seconds", defaults.dwell_scale.total_seconds())),
        horizons=tuple(timedelta(minutes=m) for m in raw["horizons_minutes"])
        if "horizons_minutes" in raw
        else defaults.horizons,
        deep_threshold=raw.get("deep_threshold", defaults.deep_threshold),
    )
