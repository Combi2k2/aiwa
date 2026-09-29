from concurrent.futures import Future
from datetime import datetime, timedelta, timezone

from aiwa.config import parse
from aiwa.core.classifier import ClassificationLoop, Question
from aiwa.core.events import Category, Segment
from aiwa.core.store import Store

T0 = datetime(2026, 9, 28, 9, 0, tzinfo=timezone.utc)
CONFIG = {
    "track": [{"app": "Google Chrome"}, {"app": "Notes"}, {"app": "Code"}],
    "category": [{"app": "Code", "category": "deep"}],
    "classification": {"suggest_after_seconds": 2, "ask_after_seconds": 10},
    "openjev": {"min_confidence": 0.7},
}


def at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


def tab(domain: str) -> Segment:
    return Segment(T0, T0, "Google Chrome", url=f"https://{domain}/page")


class InlineExecutor:
    """Runs submitted work immediately, so tests don't need threads."""

    def __init__(self):
        self.calls = []

    def submit(self, fn, *args):
        self.calls.append(args)
        future = Future()
        future.set_result(fn(*args))
        return future


class PendingExecutor:
    """Never finishes, like a slow network call."""

    def submit(self, fn, *args):
        return Future()


def loop(tmp_path, suggest=None, executor=None):
    return ClassificationLoop(parse(CONFIG), Store(tmp_path / "db"), suggest, executor)


def test_asks_the_user_10_seconds_after_switching(tmp_path):
    c = loop(tmp_path)
    assert c.observe(tab("github.com"), at(0)) is None
    assert c.observe(tab("github.com"), at(9)) is None
    assert c.observe(tab("github.com"), at(10)) == Question("classify", "github.com")


def test_switching_away_restarts_the_clock(tmp_path):
    c = loop(tmp_path)
    c.observe(tab("github.com"), at(0))
    c.observe(tab("news.com"), at(8))
    assert c.observe(tab("github.com"), at(12)) is None  # only 0 s back on github.com
    assert c.observe(tab("github.com"), at(22)) == Question("classify", "github.com")


def test_openjev_is_asked_2_seconds_after_switching_and_only_once(tmp_path):
    executor = InlineExecutor()
    c = loop(tmp_path, suggest=lambda _: (Category.DEEP, 0.95), executor=executor)
    c.observe(tab("github.com"), at(0))
    c.observe(tab("github.com"), at(1))
    assert executor.calls == []  # a quick flick past a tab costs nothing
    c.observe(tab("github.com"), at(2))
    c.observe(tab("github.com"), at(4))
    assert executor.calls == [("the website github.com",)]  # domain only


def test_confident_openjev_answer_is_shown_for_confirmation(tmp_path):
    c = loop(tmp_path, suggest=lambda _: (Category.DEEP, 0.95), executor=InlineExecutor())
    c.observe(tab("github.com"), at(0))
    c.observe(tab("github.com"), at(2))  # openjev asked
    assert c.observe(tab("github.com"), at(4)) == Question("confirm", "github.com")
    c.answered(Question("confirm", "github.com"), "ok", at(5))
    known = c.store.get_classification("github.com")
    assert (known.category, known.source, known.confirmed) == (Category.DEEP, "openjev", True)
    assert c.observe(tab("github.com"), at(60)) is None


def test_changing_openjevs_answer_makes_it_the_users(tmp_path):
    c = loop(tmp_path, suggest=lambda _: (Category.DEEP, 0.95), executor=InlineExecutor())
    c.observe(tab("youtube.com"), at(0))
    c.observe(tab("youtube.com"), at(2))
    c.answered(Question("confirm", "youtube.com"), "distraction", at(5))
    known = c.store.get_classification("youtube.com")
    assert (known.category, known.source) == (Category.DISTRACTION, "user")


def test_unsure_openjev_answer_means_the_user_is_asked_at_10_seconds(tmp_path):
    c = loop(tmp_path, suggest=lambda _: (Category.SHALLOW, 0.5), executor=InlineExecutor())
    c.observe(tab("example.org"), at(0))
    c.observe(tab("example.org"), at(2))
    assert c.observe(tab("example.org"), at(8)) is None
    assert c.observe(tab("example.org"), at(10)) == Question("classify", "example.org")
    guess = c.suggestion("example.org")
    assert (guess.category, guess.confidence) == (Category.SHALLOW, 0.5)


def test_waits_briefly_for_a_slow_openjev_then_asks_anyway(tmp_path):
    c = loop(tmp_path, suggest=lambda _: None, executor=PendingExecutor())
    c.observe(tab("github.com"), at(0))
    c.observe(tab("github.com"), at(2))
    assert c.observe(tab("github.com"), at(10)) is None
    assert c.observe(tab("github.com"), at(15)) == Question("classify", "github.com")


def test_user_answer_wins_and_is_final(tmp_path):
    c = loop(tmp_path)
    c.observe(tab("github.com"), at(0))
    c.answered(Question("classify", "github.com"), "deep", at(15))
    assert c.observe(tab("github.com"), at(60)) is None
    assert c.store.get_classification("github.com").source == "user"


def test_ask_later_backs_off_for_that_key_only(tmp_path):
    c = loop(tmp_path)
    c.observe(tab("github.com"), at(0))
    c.answered(Question("classify", "github.com"), "later", at(10))
    assert c.observe(tab("github.com"), at(60)) is None
    c.observe(tab("news.com"), at(61))
    assert c.observe(tab("news.com"), at(71)) == Question("classify", "news.com")


def test_never_classifies_rule_covered_whole_browser_internal_or_away(tmp_path):
    c = loop(tmp_path)
    for segment in [
        Segment(T0, T0, "Code"),  # decided by a config rule
        Segment(T0, T0, "Google Chrome"),  # no website known
        Segment(T0, T0, "Google Chrome", url="chrome://settings"),  # browser-internal
        Segment(T0, T0, "(away)", away=True),
    ]:
        c.observe(segment, at(0))
        assert c.observe(segment, at(60)) is None


def test_desktop_apps_are_described_as_apps(tmp_path):
    executor = InlineExecutor()
    c = loop(tmp_path, suggest=lambda _: (Category.NEUTRAL, 0.9), executor=executor)
    c.observe(Segment(T0, T0, "Notes"), at(0))
    c.observe(Segment(T0, T0, "Notes"), at(2))
    assert executor.calls == [("the desktop app Notes",)]


def test_untracked_app_gets_a_track_question_after_5_seconds(tmp_path):
    c = loop(tmp_path)
    assert c.observe(Segment(T0, T0, "Blender"), at(0)) is None
    assert c.observe(Segment(T0, T0, "Blender"), at(4)) is None
    assert c.observe(Segment(T0, T0, "Blender"), at(5)) == Question("track", "Blender")


def test_one_answer_tracks_and_classifies_with_no_second_question(tmp_path):
    c = loop(tmp_path)
    c.observe(Segment(T0, T0, "Blender"), at(0))
    c.answered(Question("track", "Blender"), "deep", at(5))
    assert c.config.is_tracked("Blender", "")
    assert c.store.tracked_apps() == ["Blender"]
    assert c.store.get_classification("Blender").category is Category.DEEP
    for t in (6, 30, 120):
        assert c.observe(Segment(T0, T0, "Blender"), at(t)) is None


def test_dont_track_is_remembered_without_the_name(tmp_path):
    c = loop(tmp_path)
    c.answered(Question("track", "Secret App"), "never", at(0))
    c.observe(Segment(T0, T0, "Secret App"), at(1))
    assert c.observe(Segment(T0, T0, "Secret App"), at(60)) is None
    names = c.store._db.execute("SELECT app FROM tracking").fetchall()
    assert names == [(None,)]  # only a hash is stored


def test_track_questions_never_reach_openjev(tmp_path):
    executor = InlineExecutor()
    c = loop(tmp_path, suggest=lambda _: (Category.DEEP, 0.9), executor=executor)
    c.observe(Segment(T0, T0, "Spotify"), at(0))
    c.observe(Segment(T0, T0, "Spotify"), at(20))
    assert executor.calls == []


def test_no_track_question_for_system_windows_or_partly_tracked_apps(tmp_path):
    config = dict(CONFIG, track=CONFIG["track"] + [{"app": "Safari", "title": "GitHub"}])
    c = ClassificationLoop(parse(config), Store(tmp_path / "db"), None, None)
    for segment in [Segment(T0, T0, "loginwindow"), Segment(T0, T0, "Safari", "News")]:
        c.observe(segment, at(0))
        assert c.observe(segment, at(60)) is None


def test_ignore_apps_setting_and_system_windows_are_never_asked_about(tmp_path):
    from datetime import datetime, timedelta, timezone

    from aiwa.config import Config
    from aiwa.core.classifier import ClassificationLoop
    from aiwa.core.events import Segment
    from aiwa.core.store import Store

    config = Config(ignore_apps=["Raycast"])
    loop = ClassificationLoop(config, Store(tmp_path / "db"), None, None)
    now = datetime.now(timezone.utc)
    for app in ["Raycast", "loginwindow"]:
        assert loop._question_for(Segment(now - timedelta(minutes=1), now, app)) is None
