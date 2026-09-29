"""The evening "plan tomorrow" dialog: block start, the one task, the warm-up."""

from __future__ import annotations

from datetime import date, time
from typing import Callable

from PySide6.QtCore import QTime, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTimeEdit, QVBoxLayout, QWidget,
)

OnSave = Callable[[date, time, str, str], None]


class PlanDialog(QWidget):
    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)  # see ui/popup.py
        self.setWindowTitle("aiwa: plan tomorrow")
        self._day: date | None = None
        self._on_save: OnSave | None = None
        self._on_later: Callable[[], None] | None = None

        self._title = QLabel(wordWrap=True)
        self._start = QTimeEdit(displayFormat="HH:mm")
        self._task = QLineEdit(placeholderText="e.g. write the methods section")
        self._warmup = QLineEdit(placeholderText="e.g. coffee, reply to 2 emails, review notes")
        form = QFormLayout()
        form.addRow("Deep-work block starts at", self._start)
        form.addRow("The one task", self._task)
        form.addRow("Warm-up before it", self._warmup)

        save, later = QPushButton("Save plan"), QPushButton("Later")
        save.setDefault(True)
        save.clicked.connect(self._save)
        later.clicked.connect(self._later)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(later)
        buttons.addWidget(save)

        layout = QVBoxLayout(self)
        layout.addWidget(self._title)
        layout.addLayout(form)
        layout.addLayout(buttons)
        self.setFixedWidth(460)

    def ask(self, day: date, start: time, task: str, warmup: str, on_save: OnSave, on_later: Callable[[], None]) -> None:
        self._day, self._on_save, self._on_later = day, on_save, on_later
        self._title.setText(f"<b>Plan {day:%A, %d %B}</b><br>"
                            "Decide tonight, so tomorrow morning starts without any decisions.")
        self._start.setTime(QTime(start.hour, start.minute))
        self._task.setText(task)
        self._warmup.setText(warmup)
        self.adjustSize()
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.center().x() - self.width() // 2, screen.top() + 80)
        self.show()
        self.raise_()
        self.activateWindow()
        self._task.setFocus()

    def _save(self) -> None:
        t = self._start.time()
        self.hide()
        if self._on_save and self._day:
            self._on_save(self._day, time(t.hour(), t.minute()), self._task.text().strip(), self._warmup.text().strip())

    def _later(self) -> None:
        self.hide()
        if self._on_later:
            self._on_later()
