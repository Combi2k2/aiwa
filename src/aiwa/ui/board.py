"""Scoreboard text for the tray menu (plain functions, no Qt)."""

from __future__ import annotations

from aiwa.core.scoreboard import DayScore

ACTIVITY_ORDER = ["deep", "shallow", "distraction", "neutral", "unclassified", "untracked", "away"]


def duration(minutes: int) -> str:
    return f"{minutes // 60}h {minutes % 60:02d}m" if minutes >= 60 else f"{minutes}m"


def scoreboard_lines(day: DayScore, threshold: float) -> list[str]:
    bar_len = 10
    filled = int(day.goal_progress * bar_len)  # full only once the goal is actually reached
    activities = " · ".join(
        f"{name.capitalize()} {duration(day.minutes_by_activity[name])}"
        for name in ACTIVITY_ORDER
        if day.minutes_by_activity.get(name)
    )
    return [
        f"Today: {day.deep_minutes} min of deep work (focus ≥ {threshold})",
        f"Longest streak {day.longest_streak} min · current streak {day.current_streak} min",
        f"Goal {day.deep_minutes}/{day.goal_minutes} min  {'▓' * filled}{'░' * (bar_len - filled)}  {day.goal_progress:.0%}",
        f"Time on: {activities}" if activities else "Time on: nothing recorded yet",
    ]
