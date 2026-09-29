import sys

from aiwa.services.activitywatch import ActivityWatchSupervisor, find_commands

SLEEPER = [sys.executable, "-c", "import time; time.sleep(60)"]


def supervisor(tmp_path, server_up=lambda: False):
    commands = {"aw-server": SLEEPER, "aw-watcher-afk": SLEEPER, "aw-watcher-window": SLEEPER}
    return ActivityWatchSupervisor(commands, server_up, tmp_path / "logs", startup_timeout=0.1)


def test_starts_every_module_and_stops_them(tmp_path):
    s = supervisor(tmp_path)
    s.start()
    processes = list(s.processes.values())
    assert list(s.processes) == ["aw-server", "aw-watcher-afk", "aw-watcher-window"]
    assert all(p.poll() is None for p in processes)
    s.stop()
    assert all(p.poll() is not None for p in processes) and s.processes == {}


def test_leaves_an_already_running_activitywatch_alone(tmp_path):
    s = supervisor(tmp_path, server_up=lambda: True)
    assert "already running" in s.start()
    assert s.processes == {} and s.check() == []


def test_restarts_a_module_that_crashed(tmp_path):
    s = supervisor(tmp_path)
    s.start()
    crashed = s.processes["aw-watcher-afk"]
    crashed.kill()
    crashed.wait()
    assert s.check() == ["aw-watcher-afk"]
    assert s.processes["aw-watcher-afk"] is not crashed
    s.stop()


def test_finds_commands_with_the_server_first(tmp_path):
    for name in ("aw-watcher-window", "aw-server"):
        (tmp_path / name).touch()
    commands = find_commands([tmp_path / "missing", tmp_path], "", ["aw-watcher-window", "aw-server"])
    assert list(commands) == ["aw-server", "aw-watcher-window"]
    assert find_commands([tmp_path], "", ["aw-server", "aw-watcher-afk"]) is None


def test_takes_over_programs_left_behind_by_a_crashed_run(tmp_path):
    first = supervisor(tmp_path)
    first.start()
    leftovers = list(first.processes.values())  # the first run "crashes": never calls stop()
    second = supervisor(tmp_path)
    second.start()
    for p in leftovers:
        p.wait(timeout=5)  # the old ones were stopped...
    assert all(p.poll() is None for p in second.processes.values())  # ...and fresh ones started
    second.stop()


def test_find_commands_in_per_program_folders(tmp_path):
    # the Windows / Linux layout: activitywatch/aw-server/aw-server.exe
    for module in ["aw-server", "aw-watcher-afk"]:
        (tmp_path / module).mkdir()
        (tmp_path / module / f"{module}.exe").write_text("")
    commands = find_commands([tmp_path], ".exe", ["aw-watcher-afk", "aw-server"])
    assert list(commands) == ["aw-server", "aw-watcher-afk"]
    assert commands["aw-server"] == [str(tmp_path / "aw-server" / "aw-server.exe")]
