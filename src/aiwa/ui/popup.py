from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


NUDGE_OPTIONS = [("Got it", "ok"), ("Snooze 30 min", "snooze"), ("Dismiss", "dismissed")]


class Popup(QWidget):
    """Small floating panel in the top-right corner that asks for a response."""

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        # aiwa is a background app that is never "active"; without these, macOS
        # hides tool windows of inactive apps, and showing one would steal focus.
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._on_response: Callable[[str], None] | None = None
        self._label = QLabel(wordWrap=True)
        self._buttons = QHBoxLayout()
        layout = QVBoxLayout(self)
        layout.addWidget(self._label)
        layout.addLayout(self._buttons)
        self.setFixedWidth(420)

    def ask(
        self,
        message: str,
        on_response: Callable[[str], None],
        options: list[tuple[str, str]] = NUDGE_OPTIONS,
    ) -> None:
        """Show `message` with one button per (label, response) option."""
        self._label.setText(message)
        self._on_response = on_response
        while self._buttons.count():
            self._buttons.takeAt(0).widget().deleteLater()
        for text, response in options:
            button = QPushButton(text)
            button.clicked.connect(lambda _=False, r=response: self._respond(r))
            self._buttons.addWidget(button)
        self.adjustSize()
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 16, screen.top() + 16)
        self.show()
        self.raise_()

    def _respond(self, response: str) -> None:
        self.hide()
        if self._on_response:
            self._on_response(response)
