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
        on_quit: Callable[[], None],
    ):
        icon = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self._icon = QSystemTrayIcon(icon)
        self._menu = QMenu()
        self._status = self._menu.addAction("aiwa: starting…")
        self._status.setEnabled(False)
        self._menu.addSeparator()
        for label, callback in [
            ("Rate my focus now…", on_rate),
            ("Small-task inbox", on_inbox),
            ("Snooze nudges for 1 hour", on_snooze),
            ("Quit aiwa", on_quit),
        ]:
            action = QAction(label, self._menu)
            action.triggered.connect(callback)
            self._menu.addAction(action)
        self._icon.setContextMenu(self._menu)
        self._icon.setToolTip("aiwa")
        self._icon.show()

    def set_status(self, text: str) -> None:
        self._status.setText(f"aiwa: {text}")
        self._icon.setToolTip(f"aiwa: {text}")

    def notify(self, title: str, message: str) -> None:
        self._icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information)
