from datetime import date, datetime, time, timedelta, timezone

from aiwa.core.history import DayOutcome, chain_length, deep_minutes
from aiwa.core.rhythm import Rhythm
from aiwa.core.schedule import BlockReminders, Plan, Reminder, RhythmParams, block_for
from aiwa.core.scoreboard.ledger import MinuteEntry
from aiwa.core.store import Store
from aiwa.ui.board import rhythm_lines

UTC = timezone.utc
MON = date(2026, 9, 28)  # a Monday
PARAMS = RhythmParams()


# --- schedule.py ---------------------------------------------------------------

def test_default_block_on_weekdays_only():
    block = block_for(MON, PARAMS, None, UTC)
    assert block.start == datetime(2026, 9, 28, 9, 0, tzinfo=UTC)
    assert block.end == block.start + timedelta(minutes=90)
    assert block_for(date(2026, 10, 4), PARAMS, None, UTC) is None  # Sunday


def test_a_plan_overrides_the_rhythm_even_on_a_day_off():
    plan = Plan(date(2026, 10, 4), time(7, 30), "write intro", "tea + notes")
    block = block_for(date(2026, 10, 4), PARAMS, plan, UTC)
    assert block.start.time() == time(7, 30) and block.task == "write intro"


def reminders(warmup="coffee + notes"):
    block = block_for(MON, PARAMS, Plan(MON, time(9, 0), "task", warmup), UTC)
    return BlockReminders(block, timedelta(minutes=20))


def at(hh, mm):
    return datetime(2026, 9, 28, hh, mm, tzinfo=UTC)


def test_warmup_then_start_reminder():
    r = reminders()
    assert r.due(at(8, 30), in_session=False) is None
    assert r.due(at(8, 40), in_session=False) is Reminder.WARMUP
    r.shown(Reminder.WARMUP)
    assert r.due(at(8, 50), in_session=False) is None
    assert r.due(at(9, 0), in_session=False) is Reminder.START


def test_no_warmup_reminder_without_a_planned_warmup():
    assert reminders(warmup="").due(at(8, 45), in_session=False) is None


def test_snooze_asks_again_after_10_minutes_and_skip_stops_it():
    r = reminders()
    r.shown(Reminder.START)
    r.snooze(at(9, 0))
    assert r.due(at(9, 5), in_session=False) is None
    assert r.due(at(9, 10), in_session=False) is Reminder.START
    r.skip()
    assert r.due(at(9, 20), in_session=False) is None


def test_no_reminder_in_a_session_or_after_the_block():
    r = reminders()
    assert r.due(at(9, 5), in_session=True) is None
    assert r.due(at(10, 31), in_session=False) is None


# --- history.py ------------------------------------------------------------------

def test_deep_minutes_in_a_session():
    entries = [MinuteEntry(at(9, m), 0.8 if m < 30 else 0.2, "deep") for m in range(45)]
    assert deep_minutes(entries, at(9, 0), at(9, 45), 0.6) == 30


def test_chain_counts_kept_days_and_breaks_on_a_miss():
    days = [MON - timedelta(days=i) for i in range(5)]
    outcomes = [DayOutcome(days[0], kept=False), DayOutcome(days[1], True), DayOutcome(days[2], True),
                DayOutcome(days[3], False), DayOutcome(days[4], True)]
    assert chain_length(outcomes, today=MON) == 2  # today still open; yesterday and the day before kept


def test_chain_includes_today_once_kept_and_breaks_on_a_skip():
    assert chain_length([DayOutcome(MON, True), DayOutcome(MON - timedelta(days=1), True)], MON) == 2
    assert chain_length([DayOutcome(MON, False, skipped=True), DayOutcome(MON - timedelta(days=1), True)], MON) == 0


# --- rhythm.py (with the store) ----------------------------------------------------

def test_a_block_is_kept_with_enough_deep_work_in_a_session(tmp_path):
    store = Store(tmp_path / "db")
    rhythm = Rhythm(store, PARAMS, time(0, 0), deep_threshold=0.6)
    session = store.start_session(at(9, 2))
    store.save_minutes([MinuteEntry(at(9, 2) + timedelta(minutes=m), 0.9, "deep") for m in range(30)])
    store.end_session(session, at(9, 40), {}, "user")
    now = at(12, 0)
    assert rhythm.outcome(MON, UTC, now).kept
    assert rhythm.todays_sessions(now)[0].deep_minutes == 30


def test_plans_round_trip(tmp_path):
    store = Store(tmp_path / "db")
    store.save_plan(MON, time(8, 15), "task", "warm-up", at(21, 30))
    assert store.get_plan(MON) == Plan(MON, time(8, 15), "task", "warm-up")


# --- board.py ----------------------------------------------------------------------

def test_rhythm_lines():
    block = block_for(MON, PARAMS, Plan(MON, time(9, 0), "write intro"), UTC)
    lines = rhythm_lines(block, at(8, 0), chain=3, sessions=[])
    assert lines[0].startswith("Deep-work block today: ") and lines[0].endswith("· write intro")
    assert lines[1] == "Chain: 3 days in a row"
