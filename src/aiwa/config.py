"""User settings, loaded from a TOML file in the OS config directory."""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from datetime import time, timedelta
from pathlib import Path

from platformdirs import user_config_path, user_data_path

from aiwa.core.events import Category
from aiwa.core.focus.params import FocusParams
from aiwa.core.sampling import SamplingParams

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
horizons_minutes = [2, 10, 30]  # sliding-window sizes; the middle one is the main score
shallow_weight = 0.3            # depth: how much shallow time counts (deep 1, distraction 0)
capacity = 5                    # stability: items a focused working set can hold
dwell_scale_seconds = 20        # continuity: mean time per item that scores 0.63
deep_threshold = 0.6            # a minute counts as deep work at this intensity or above

[sampling]
# A few times a day aiwa asks "how focused are you right now? (1–5)" at random
# moments, to calibrate the focus score to you (see `aiwa calibrate`).
enabled = true
per_day = 5
start = "09:00"
end = "18:00"
min_gap_minutes = 45

[classification]
suggest_after_seconds = 2    # ask openjev about an unclassified app/website after this long on it
ask_after_seconds = 10       # ask you, if still unclassified or openjev is unsure, after this long
ask_track_after_seconds = 5  # ask whether to track an untracked app after using it this long

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
    ask_track_after_seconds: int = 5
    focus: FocusParams = field(default_factory=FocusParams)
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
        path.write_text(DEFAULT_CONFIG)
    return parse(tomllib.loads(path.read_text()))


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
        ask_track_after_seconds=classification.get("ask_track_after_seconds", 5),
        focus=parse_focus(focus),
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
