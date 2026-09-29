from datetime import date, datetime, time, timedelta

from aiwa.core.offtime import OffTimeParams, near, off_time, often_missed
from aiwa.core.shutdown import ShutdownParams, lowness, shift_ending, time_weight, workday

TUESDAY, SATURDAY = date(2026, 9, 29), date(2026, 10, 3)
P = ShutdownParams()


def local(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute)).astimezone()


def test_time_weight_is_an_s_curve_around_the_shutdown_time():
    six = local(TUESDAY, 18)
    weight = lambda h, m=0: round(time_weight(local(TUESDAY, h, m), six, P.spread), 2)
    assert weight(16) == 0.01 and weight(17) == 0.1 and weight(17, 30) == 0.25
    assert weight(18) == 0.5 and weight(18, 30) == 0.75 and weight(19) == 0.9


def test_lowness():
    assert lowness(None, 0.6) == 1.0
    assert lowness(0.6, 0.6) == 0.0 and lowness(0.8, 0.6) == 0.0
    assert lowness(0.3, 0.6) == 0.5


def test_offered_when_focus_is_low_around_the_shutdown_time_never_while_focused():
    def ending(hour, minute, intensity):
        return shift_ending(local(TUESDAY, hour, minute), TUESDAY, time(4), P, intensity) >= P.offer_at

    assert not ending(16, 0, None) and not ending(17, 30, None)  # idle, but too early
    assert ending(18, 0, None)
    assert ending(18, 30, 0.1)  # reading email
    assert not ending(18, 30, 0.3)
    assert ending(19, 0, 0.2)
    assert not ending(20, 0, 0.7)  # focused: never interrupt that


def test_workdays_only_by_default():
    assert workday(TUESDAY, P) and not workday(SATURDAY, P)
    assert shift_ending(local(SATURDAY, 19), SATURDAY, time(4), P, None) == 0
    assert not workday(TUESDAY, ShutdownParams(enabled=False))


def test_off_time_is_the_peak_of_long_stops():
    stops = []
    for d in range(7):
        day = TUESDAY - timedelta(days=d)
        stops.append(local(day, 17, 35 + d % 3 * 5))  # 17:35–17:45, most days
    stops += [local(TUESDAY - timedelta(days=d), 23, 50) for d in (1, 3)]  # some nights straight to bed
    assert off_time(stops, time(4)) == time(17, 40)


def test_off_time_around_midnight():
    stops = [local(TUESDAY - timedelta(days=d), 23, 50) for d in range(3)]
    stops += [local(TUESDAY - timedelta(days=d), 0, 10) for d in range(3, 6)]  # after midnight: still late, not early
    assert off_time(stops, time(4)) == time(0, 0)


def test_off_time_needs_enough_days():
    stops = [local(TUESDAY - timedelta(days=d), 17, 40) for d in range(4)]
    assert off_time(stops, time(4)) is None


def test_near_and_often_missed():
    assert near(local(TUESDAY, 17, 20), time(17, 40))
    assert not near(local(TUESDAY, 16, 50), time(17, 40))
    assert not near(local(TUESDAY, 17, 40), None)
    assert often_missed([False, True, False, False, True])
    assert not often_missed([False, True, True, False, True])
