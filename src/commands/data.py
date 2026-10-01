"""Loads categorized, privacy-masked segments for a time range. Used by every command."""

from __future__ import annotations

from datetime import datetime

from aiwa import config as config_mod
from aiwa.core.categories import Categorizer, prepare
from aiwa.core.collector import Collector
from aiwa.core.events import Segment
from aiwa.core.store import Store


class ActivityWatchUnavailable(Exception):
    pass


def load_segments(config: config_mod.Config, start: datetime, end: datetime) -> list[Segment]:
    try:
        raw = Collector(config).between(start, end)
    except (OSError, RuntimeError) as e:
        raise ActivityWatchUnavailable(
            f"Cannot read from ActivityWatch at {config.aw_host}:{config.aw_port}: {e}"
        ) from e
    store = Store(config_mod.DB_PATH)
    config.add_tracked_apps(store.tracked_apps())
    return prepare(raw, config, Categorizer(config.categories, store))
