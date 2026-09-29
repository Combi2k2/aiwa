"""Learning the user's routines from their absences ("what was that?").

An absence runs from the last activity to the next one: away from the keyboard,
or the laptop asleep / aiwa not running. After it, aiwa asks what it was, at
random, more often for longer absences. Overnight absences are logged as sleep
without asking. The answers (and the unasked absences) build up typical times
for meals, sport, etc., which later routine reminders use.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, time, timedelta

# two levels: category → activities (key, label)
TAXONOMY: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "body_care": ("Body care", [("toilet", "Toilet"), ("shower", "Shower"), ("grooming", "Getting ready")]),
    "food": ("Food", [("coffee_snack", "Coffee / snack"), ("cooking", "Cooking"), ("meal", "A meal")]),
    "movement": ("Movement", [("workout", "Sport / workout"), ("walk", "A walk"), ("stretching", "Stretching")]),
    "rest": ("Rest", [("nap", "A nap"), ("sleep", "Sleep"), ("relax", "Relaxing")]),
    "chores": ("Chores", [("cleaning", "Cleaning"), ("laundry", "Laundry"), ("errands", "Shopping / errands")]),
    "people": ("People", [("family_friends", "Family / friends"), ("phone_call", "Phone call"), ("meeting", "Meeting in person")]),
    "out": ("Out", [("commute", "Commute"), ("travel", "Travel"), ("appointment", "Appointment")]),
    "offline_work": ("Offline work", [("reading_paper", "Reading on paper"), ("handwriting", "Working by hand"), ("thinking", "Thinking it through")]),
    "leisure": ("Leisure", [("tv", "TV / video"), ("games", "Games"), ("hobby", "A hobby")]),
}
ACTIVITY_CATEGORY = {key: cat for cat, (_, items) in TAXONOMY.items() for key, _ in items}
ACTIVITY_LABEL = {key: label for _, (_, items) in TAXONOMY.items() for key, label in items}

MIN_ABSENCE = timedelta(minutes=5)
MEAL_HOURS = [(7, 10), (11, 14), (17, 21)]


def ask_probability(duration: timedelta) -> float:
    """How likely aiwa asks about an absence of this length."""
    minutes = duration.total_seconds() / 60
    if minutes < 5:
        return 0.0
    if minutes < 20:
        return 0.2  # toilet, coffee: mostly not worth asking
    if minutes < 60:
        return 0.6
    if minutes < 180:
        return 0.8
    return 0.5  # very long: sleep, a day out, offline work


def likely_activities(duration: timedelta, start: datetime, limit: int = 5) -> list[str]:
    """The activities most likely for an absence this long at this time of day, best first."""
    minutes = duration.total_seconds() / 60
    hour = start.astimezone().hour
    mealtime = any(a <= hour < b for a, b in MEAL_HOURS)
    if minutes < 20:
        options = ["toilet", "coffee_snack", "stretching", "phone_call", "relax"]
    elif minutes < 60:
        options = (["meal", "cooking"] if mealtime else ["cooking", "meal"]) + ["shower", "workout", "walk", "cleaning", "nap"]
    elif minutes < 180:
        options = (["meal"] if mealtime else []) + ["workout", "errands", "family_friends", "nap", "appointment", "meal"]
    else:
        options = ["sleep", "travel", "commute", "reading_paper", "family_friends"]
    return list(dict.fromkeys(options))[:limit]


@dataclass(frozen=True)
class Absence:
    start: datetime  # last activity before it
    end: datetime  # first activity after it

    @property
    def duration(self) -> timedelta:
        return self.end - self.start


def overnight(absence: Absence, bedtime: time, day_starts: time) -> bool:
    """Whether the absence covers part of the night (bedtime until the day starts): that's sleep."""
    t = absence.start.astimezone()
    while t < absence.end:
        clock = t.time()
        if clock >= bedtime or clock < day_starts:
            return True
        t += timedelta(minutes=15)
    return False


class AbsenceTracker:
    """Turns "is the user active now?" (checked every few seconds) into finished absences."""

    def __init__(self, rng: random.Random | None = None, always_ask: bool = False):
        self.last_active: datetime | None = None
        self.returned_at: datetime | None = None  # end of the last absence
        self.rng = rng or random.Random()
        self.always_ask = always_ask  # for trying it out: ask about every absence of 5+ minutes

    def step(self, now: datetime, active: bool, away_since: datetime | None = None) -> Absence | None:
        """Call regularly; returns an absence when the user comes back from one.

        `away_since`: when ActivityWatch says the user left (their last input). It
        marks "away" only after a few idle minutes, so this is earlier than the
        moment aiwa first sees them as away.
        """
        if not active:
            if away_since is not None and self.last_active is not None:
                if self.returned_at is not None:
                    # ActivityWatch can still report the previous away period for a moment
                    # after the user is back: never reach back into an absence already reported
                    away_since = max(away_since, self.returned_at)
                self.last_active = min(self.last_active, away_since)
            return None
        previous, self.last_active = self.last_active, now
        if previous is not None and now - previous >= MIN_ABSENCE:
            self.returned_at = now
            return Absence(previous, now)
        return None

    def should_ask(self, absence: Absence) -> bool:
        if self.always_ask:
            return absence.duration >= MIN_ABSENCE
        return self.rng.random() < ask_probability(absence.duration)
