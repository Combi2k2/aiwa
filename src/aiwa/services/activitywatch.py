"""Runs ActivityWatch's background programs, so its own tray app isn't needed.

ActivityWatch's tray app (aw-qt) only starts a few programs and shows an icon.
aiwa does the same job from its own tray icon: start the server and watchers,
restart any that crash, and stop them when aiwa quits. If ActivityWatch is
already running (e.g. aw-qt was opened), aiwa leaves it alone, unless those
are programs aiwa itself started in an earlier run that ended without cleaning
up (a crash); aiwa remembers their process ids and takes them over.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Callable

import requests

SERVER = "aw-server"
DEFAULT_MODULES = [SERVER, "aw-watcher-afk", "aw-watcher-window"]
SERVER_STARTUP = 10.0  # seconds to wait for the server before starting watchers


class ActivityWatchSupervisor:
    def __init__(
        self,
        commands: dict[str, list[str]],  # module name → command line; the server first
        is_server_up: Callable[[], bool],
        log_dir: Path,
        startup_timeout: float = SERVER_STARTUP,
    ):
        self.commands = commands
        self.startup_timeout = startup_timeout
        self.is_server_up = is_server_up
        self.log_dir = log_dir
        self.processes: dict[str, subprocess.Popen] = {}
        self.external = False  # ActivityWatch was already running, managed by someone else
        self.pid_file = log_dir / "pids"

    def start(self) -> str:
        """Start everything; returns a short status for the tray."""
        if self._stop_leftovers():
            deadline = time.monotonic() + self.startup_timeout
            while self.is_server_up() and time.monotonic() < deadline:
                time.sleep(0.2)
        if self.is_server_up():
            self.external = True
            return "ActivityWatch already running (not managed by aiwa)"
        if SERVER in self.commands:
            self._launch(SERVER)
            deadline = time.monotonic() + self.startup_timeout
            while not self.is_server_up() and time.monotonic() < deadline:
                time.sleep(0.2)
        for module in self.commands:
            if module != SERVER:
                self._launch(module)
        self._save_pids()
        return "ActivityWatch started by aiwa"

    def check(self) -> list[str]:
        """Restart any module that has stopped; returns the names restarted."""
        if self.external:
            return []
        restarted = []
        for module, process in list(self.processes.items()):
            if process.poll() is not None:
                self._launch(module)
                restarted.append(module)
        if restarted:
            self._save_pids()
        return restarted

    def stop(self) -> None:
        """Stop the modules aiwa started, watchers first and the server last."""
        for module in reversed(list(self.processes)):
            process = self.processes.pop(module)
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
        self.pid_file.unlink(missing_ok=True)

    def _save_pids(self) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.pid_file.write_text("\n".join(str(p.pid) for p in self.processes.values()))

    def _stop_leftovers(self) -> bool:
        """Stop programs a previous aiwa run started but never stopped. True if any were found."""
        if not self.pid_file.exists():
            return False
        found = False
        for line in self.pid_file.read_text().split():
            pid = int(line)
            if _is_activitywatch(pid, self.commands):
                os.kill(pid, signal.SIGTERM)
                found = True
        self.pid_file.unlink()
        return found

    def _launch(self, module: str) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        log = (self.log_dir / f"{module}.log").open("ab")
        self.processes[module] = subprocess.Popen(
            self.commands[module],
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
        )


def _is_activitywatch(pid: int, commands: dict[str, list[str]]) -> bool:
    """Whether `pid` is still one of our ActivityWatch programs (pids get reused)."""
    try:
        name = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True).stdout
    except OSError:
        return False
    return any(command[0] in name for command in commands.values())


def find_commands(directories: list[Path], suffix: str, modules: list[str]) -> dict[str, list[str]] | None:
    """Command lines for `modules` from the first directory that has all of them."""
    for directory in directories:
        paths = {m: directory / f"{m}{suffix}" for m in modules}
        if all(p.exists() for p in paths.values()):
            ordered = sorted(modules, key=lambda m: m != SERVER)  # server first
            return {m: [str(paths[m])] for m in ordered}
    return None


def server_check(host: str, port: int) -> Callable[[], bool]:
    def is_up() -> bool:
        try:
            return requests.get(f"http://{host}:{port}/api/0/info", timeout=1).ok
        except requests.RequestException:
            return False

    return is_up
