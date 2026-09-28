from __future__ import annotations

from typing import Callable

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from aiwa.ui.icon import scope_icon

SCOREBOARD_LINES = 4


class Tray:
    """Menu bar (macOS) / system tray (Windows, Linux) icon with the scoreboard."""

    def __init__(
        self,
        on_rate: Callable[[], None],
        on_inbox: Callable[[], None],
        on_snooze: Callable[[], None],
        on_settings: Callable[[], None],
        on_autostart: Callable[[bool], None],
        autostart_enabled: bool,
        on_quit: Callable[[], None],
    ):
        self._icon = QSystemTrayIcon(scope_icon(0))
        self._progress = 0.0
        self._menu = QMenu()
        self._status = self._info("aiwa: starting…")
        self._board = [self._info("") for _ in range(SCOREBOARD_LINES)]
        for line in self._board:
            line.setVisible(False)
        self._menu.addSeparator()
        self._add("Rate my focus now…", on_rate)
        self._add("Small-task inbox", on_inbox)
        self._add("Snooze nudges for 1 hour", on_snooze)
        self._menu.addSeparator()
        self._add("Open settings…", on_settings)
        autostart = self._add("Start at login", lambda: None)
        autostart.setCheckable(True)
        autostart.setChecked(autostart_enabled)
        autostart.toggled.connect(on_autostart)
        self._add("Quit aiwa", on_quit)
        self._icon.setContextMenu(self._menu)
        self._icon.setToolTip("aiwa")
        self._icon.show()

    def _info(self, text: str) -> QAction:
        action = self._menu.addAction(text)
        action.setEnabled(False)  # read-only line
        return action

    def _add(self, label: str, callback: Callable[[], None]) -> QAction:
        action = QAction(label, self._menu)
        action.triggered.connect(callback)
        self._menu.addAction(action)
        return action

    def set_status(self, text: str) -> None:
        self._status.setText(f"aiwa: {text}")
        self._icon.setToolTip(f"aiwa: {text}")

    def set_scoreboard(self, lines: list[str], progress: float) -> None:
        for action, text in zip(self._board, lines):
            action.setText(text)
            action.setVisible(True)
        if round(progress, 2) != round(self._progress, 2):  # redraw only when it visibly changes
            self._progress = progress
            self._icon.setIcon(scope_icon(progress))

    def notify(self, title: str, message: str) -> None:
        self._icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information)
