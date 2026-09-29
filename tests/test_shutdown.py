from datetime import date, datetime, time

from aiwa.core.shutdown import ShutdownParams, is_due, workday

TUESDAY, SATURDAY = date(2026, 9, 29), date(2026, 10, 3)
P = ShutdownParams()


def local(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute)).astimezone()


def test_due_from_18_until_the_day_ends():
    assert not is_due(local(TUESDAY, 17, 59), TUESDAY, time(4), P)
    assert is_due(local(TUESDAY, 18), TUESDAY, time(4), P)
    assert is_due(local(date(2026, 9, 30), 1), TUESDAY, time(4), P)  # 01:00 still belongs to Tuesday


def test_workdays_only_by_default():
    assert workday(TUESDAY, P) and not workday(SATURDAY, P)
    assert not is_due(local(SATURDAY, 19), SATURDAY, time(4), P)
    assert not workday(TUESDAY, ShutdownParams(enabled=False))
