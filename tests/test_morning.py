from datetime import datetime, timedelta, timezone

from aiwa.core.morning import Action, MorningFlow, State, buffer_for

T0 = datetime(2026, 9, 30, 7, 0, tzinfo=timezone.utc)


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def test_buffer_is_20_percent_clamped_to_5_and_20_minutes():
    assert buffer_for(timedelta(minutes=10)) == timedelta(minutes=5)
    assert buffer_for(timedelta(minutes=50)) == timedelta(minutes=10)
    assert buffer_for(timedelta(minutes=200)) == timedelta(minutes=20)


def test_greets_on_the_first_activity_only():
    m = MorningFlow()
    assert m.step(at(0), active=False) is Action.NONE
    assert m.step(at(1), active=True) is Action.GREET
    assert m.step(at(2), active=True) is Action.NONE


def test_back_from_the_routine_suggests_the_session():
    m = MorningFlow()
    m.step(at(0), True)
    assert m.start_routine(at(0), 30) == at(36)  # 30 min + 6 min buffer
    for minute in range(1, 25):
        assert m.step(at(minute), active=False) is Action.NONE
    assert m.step(at(25), active=True) is Action.WELCOME_BACK
    assert m.state is State.DONE


def test_not_back_by_the_deadline_rings_until_back():
    m = MorningFlow()
    m.step(at(0), True)
    m.start_routine(at(0), 30)
    for minute in range(1, 36):
        m.step(at(minute), active=False)
    assert m.step(at(36), active=False) is Action.ALARM
    assert m.step(at(40), active=False) is Action.NONE  # keeps ringing (the app loops the sound)
    assert m.step(at(45), active=True) is Action.WELCOME_BACK
    assert not m.ringing


def test_a_quick_glance_at_the_laptop_is_not_coming_back():
    m = MorningFlow()
    m.step(at(0), True)
    m.start_routine(at(0), 30)
    m.step(at(1), active=False)
    assert m.step(at(2), active=True) is Action.NONE  # away only a minute: still in the routine


def test_still_at_the_computer_when_time_is_up():
    m = MorningFlow()
    m.step(at(0), True)
    m.start_routine(at(0), 20)
    assert m.step(at(10), active=True) is Action.NONE
    assert m.step(at(25), active=True) is Action.WELCOME_BACK  # no alarm: they're right here


def test_finish_ends_the_morning():
    m = MorningFlow()
    m.step(at(0), True)
    m.finish()
    assert m.step(at(60), active=True) is Action.NONE
