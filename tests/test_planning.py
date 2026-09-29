from datetime import date, datetime, timedelta, timezone

import requests

from aiwa.core.ai import _json_list
from aiwa.core.openjev import Openjev, assess_task
from aiwa.core.planning import Assessment, PlanningConversation, split_lines
from aiwa.core.store import Store

DAY = date(2026, 9, 30)
NOW = datetime(2026, 9, 29, 21, 30, tzinfo=timezone.utc)

# a stand-in for openjev: fixed answers per task
ASSESSMENTS = {
    "email prof about the deadline": Assessment("shallow", 15, 0.8),
    "revise for final": Assessment("deep", None, 0.1),  # vague
    "read chapter 3 (25 pages)": Assessment("deep", 85, 0.95),  # too long
    "read pages 1-12 of chapter 3": Assessment("deep", 40, 0.9),
    "read pages 13-25 of chapter 3": Assessment("deep", 40, 0.9),
    "revise chapters 1-2 of statistics": Assessment("deep", 40, 0.8),
}


def assessor(task):
    return ASSESSMENTS.get(task)


def conversation(writer=None):
    return PlanningConversation(DAY, assessor, writer)


# --- when a task needs elaboration ---------------------------------------------------

def test_needs_elaboration_rules():
    assert Assessment("shallow", 15, 0.8).needs_elaboration is None
    assert Assessment("deep", 40, 0.3).needs_elaboration == "vague"  # not specific
    assert Assessment("deep", None, 0.9).needs_elaboration == "vague"  # can't be sized
    assert Assessment("deep", 85, 0.9).needs_elaboration == "too_long"  # over one 50-min session
    assert Assessment("deep", 50, 0.9).needs_elaboration is None  # exactly one session is fine


# --- the conversation without AI (templates) -------------------------------------------

def test_atomic_tasks_are_accepted_straight_away():
    c = conversation()
    reply = c.receive("- email prof about the deadline")
    assert reply.done and [t.text for t in c.accepted] == ["email prof about the deadline"]
    assert c.accepted[0].kind == "shallow" and c.accepted[0].minutes == 15


def test_vague_and_long_tasks_are_asked_about_one_at_a_time():
    c = conversation()
    reply = c.receive("revise for final\nread chapter 3 (25 pages)\nemail prof about the deadline")
    assert not reply.done and "revise for final" in reply.messages[0] and "hard to size" in reply.messages[0]
    reply = c.receive("revise chapters 1-2 of statistics")
    assert not reply.done and "more than one focus session" in reply.messages[0]
    reply = c.receive("read pages 1-12 of chapter 3\nread pages 13-25 of chapter 3")
    assert reply.done
    assert [t.text for t in c.accepted] == [
        "email prof about the deadline",
        "revise chapters 1-2 of statistics",
        "read pages 1-12 of chapter 3",
        "read pages 13-25 of chapter 3",
    ]


def test_keep_leaves_a_task_as_the_user_wrote_it():
    c = conversation()
    c.receive("revise for final")
    assert c.receive("keep").done
    assert [t.text for t in c.accepted] == ["revise for final"]


def test_stops_asking_about_the_same_task_after_two_rounds():
    c = conversation()
    c.receive("revise for final")
    c.receive("revise for final")  # the answer is still vague
    assert c.receive("revise for final").done  # asked twice: accepted as written now


def test_without_openjev_everything_is_accepted():
    c = PlanningConversation(DAY, None, None)
    assert c.receive("anything at all\nsomething else").done
    assert len(c.accepted) == 2


def test_opening_lists_carried_over_tasks():
    text = conversation().opening(["email prof about the deadline"])
    assert "Wednesday" in text and "• email prof about the deadline" in text


def test_split_lines_removes_bullets_and_numbering():
    assert split_lines("1. one\n- two\n* three\n• four\n\n5) five") == ["one", "two", "three", "four", "five"]


# --- with an AI writer ------------------------------------------------------------------

class FakeWriter:
    def split(self, text):
        return [p.strip() for p in text.split(",")]

    def question(self, task, reason):
        return f"AI question about {task} ({reason})"

    def refine(self, task, question, answer):
        return ["revise chapters 1-2 of statistics"]


class BrokenWriter:
    def split(self, text):
        raise requests.ConnectionError("down")

    question = refine = split


def test_ai_writer_splits_asks_and_refines():
    c = conversation(FakeWriter())
    reply = c.receive("email prof about the deadline, revise for final")
    assert reply.messages == ["AI question about revise for final (vague)"]
    assert c.receive("the first two chapters").done
    assert [t.text for t in c.accepted] == ["email prof about the deadline", "revise chapters 1-2 of statistics"]


def test_a_failing_ai_falls_back_to_templates():
    c = conversation(BrokenWriter())
    reply = c.receive("revise for final")
    assert "hard to size" in reply.messages[0]


def test_json_list_parsing():
    assert _json_list('Sure!\n["a", "b"]') == ["a", "b"]
    assert _json_list("no list here") is None and _json_list("[]") is None


# --- openjev assessment -------------------------------------------------------------------

class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def test_openjev_assessment_maps_size_to_minutes(monkeypatch):
    answers = {"kind": {"choice": "deep"}, "size": {"choice": "50_to_120"}, "specific": {"noul": 0.9}}
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse({"answers": answers}))
    a = assess_task(Openjev("key"), "read chapter 3")
    assert (a.kind, a.minutes, a.specific, a.needs_elaboration) == ("deep", 85, 0.9, "too_long")


def test_openjev_unclear_size_means_vague(monkeypatch):
    answers = {"kind": {"choice": "deep"}, "size": {"choice": "unclear"}, "specific": {"noul": 0.8}}
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse({"answers": answers}))
    assert assess_task(Openjev("key"), "work on aiwa").needs_elaboration == "vague"


# --- the to-do list ---------------------------------------------------------------------------

def test_todos_carry_over_and_keep_their_order(tmp_path):
    store = Store(tmp_path / "db")
    yesterday = DAY - timedelta(days=1)
    store.add_todos(yesterday, [("old unfinished", "deep", 40)], NOW)
    store.add_todos(DAY, [("first", "deep", 40), ("second", "shallow", 15)], NOW)
    assert [t.text for t in store.open_todos(DAY)] == ["old unfinished", "first", "second"]
    assert store.todos_planned_for(DAY) == 2


def test_done_and_pick_another(tmp_path):
    store = Store(tmp_path / "db")
    store.add_todos(DAY, [("first", None, None), ("second", None, None)], NOW)
    first, second = store.open_todos(DAY)
    store.move_todo_to_end(first.id, DAY)
    assert [t.text for t in store.open_todos(DAY)] == ["second", "first"]
    store.set_todo_status(second.id, "done", NOW)
    assert [t.text for t in store.open_todos(DAY)] == ["first"]
    assert store.todos_done_between(NOW - timedelta(hours=1), NOW + timedelta(hours=1)) == 1
