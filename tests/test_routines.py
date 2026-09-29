import random
from datetime import datetime, time, timedelta

from aiwa.core.routines import (
    ACTIVITY_CATEGORY, TAXONOMY, Absence, AbsenceTracker, ask_probability, likely_activities, overnight,
)

T0 = datetime(2026, 9, 30, 12, 0).astimezone()


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def test_every_activity_has_one_category():
    keys = [key for _, (_, items) in TAXONOMY.items() for key, _ in items]
    assert len(keys) == len(set(keys)) == len(ACTIVITY_CATEGORY)


def test_ask_probability_by_duration():
    assert ask_probability(timedelta(minutes=4)) == 0
    assert ask_probability(timedelta(minutes=10)) == 0.2
    assert ask_probability(timedelta(minutes=45)) == 0.6
    assert ask_probability(timedelta(hours=2)) == 0.8
    assert ask_probability(timedelta(hours=5)) == 0.5


def test_likely_activities_depend_on_duration_and_time_of_day():
    assert likely_activities(timedelta(minutes=10), T0)[0] == "toilet"
    assert likely_activities(timedelta(minutes=40), T0)[0] == "meal"  # noon: lunch first
    afternoon = T0.replace(hour=15)
    assert likely_activities(timedelta(minutes=40), afternoon)[0] == "cooking"
    assert len(likely_activities(timedelta(minutes=40), T0)) == 5
    assert likely_activities(timedelta(hours=6), T0)[0] == "sleep"


def test_tracker_reports_an_absence_when_the_user_comes_back():
    tracker = AbsenceTracker()
    assert tracker.step(at(0), True) is None
    for minute in range(1, 30):
        assert tracker.step(at(minute), False) is None
    absence = tracker.step(at(30), True)
    assert absence == Absence(at(0), at(30))


def test_laptop_sleep_is_an_absence_too():
    tracker = AbsenceTracker()
    tracker.step(at(0), True)
    # no calls at all while the Mac sleeps
    assert tracker.step(at(90), True) == Absence(at(0), at(90))


def test_short_breaks_are_not_absences():
    tracker = AbsenceTracker()
    tracker.step(at(0), True)
    tracker.step(at(2), False)
    assert tracker.step(at(4), True) is None


def test_should_ask_follows_the_probability():
    tracker = AbsenceTracker(random.Random(1))
    asked = sum(tracker.should_ask(Absence(at(0), at(40))) for _ in range(1000))
    assert 550 < asked < 650  # about 60%


def test_overnight():
    night = Absence(T0.replace(hour=23, minute=30), T0.replace(hour=7) + timedelta(days=1))
    day = Absence(T0, at(90))
    assert overnight(night, time(22), time(4))
    assert not overnight(day, time(22), time(4))


def test_absences_round_trip(tmp_path):
    from aiwa.core.store import Store

    store = Store(tmp_path / "db")
    absence_id = store.add_absence(at(0), at(40), None, "unasked")
    store.set_absence_activity(absence_id, "meal", "user")
    ((start, end, activity, source),) = store.absences()
    assert (end - start, activity, source) == (timedelta(minutes=40), "meal", "user")


def test_always_ask_for_trying_it_out():
    tracker = AbsenceTracker(random.Random(1), always_ask=True)
    assert all(tracker.should_ask(Absence(at(0), at(6))) for _ in range(20))
