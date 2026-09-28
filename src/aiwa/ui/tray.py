from __future__ import annotations

from typing import Callable

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon


class Tray:
    """Menu bar (macOS) / system tray (Windows, Linux) icon."""

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
        icon = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self._icon = QSystemTrayIcon(icon)
        self._menu = QMenu()
        self._status = self._menu.addAction("aiwa: starting…")
        self._status.setEnabled(False)
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

    def _add(self, label: str, callback: Callable[[], None]) -> QAction:
        action = QAction(label, self._menu)
        action.triggered.connect(callback)
        self._menu.addAction(action)
        return action

    def set_status(self, text: str) -> None:
        self._status.setText(f"aiwa: {text}")
        self._icon.setToolTip(f"aiwa: {text}")

    def notify(self, title: str, message: str) -> None:
        self._icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information)
