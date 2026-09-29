"""The planning conversation window: the user lists tasks, aiwa asks about vague or
too-big ones, and the result is saved to the to-do list."""

from __future__ import annotations

import html
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from aiwa.core.planning import DraftTask, PlanningConversation, Reply


class PlanChat(QWidget):
    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)  # see ui/popup.py
        self.setWindowTitle("aiwa: plan")
        self._conversation: PlanningConversation | None = None
        self._on_save: Callable[[list[DraftTask]], None] | None = None
        self._on_later: Callable[[], None] | None = None
        self._pool = ThreadPoolExecutor(max_workers=1)  # openjev + AI calls block; keep them off the UI
        self._pending: Future | None = None
        self._poll = QTimer(interval=150)
        self._poll.timeout.connect(self._check_reply)

        self._log = QTextBrowser()
        self._input = QPlainTextEdit(placeholderText="One task per line…")
        self._input.setFixedHeight(90)
        self._busy = QLabel("")
        self._send = QPushButton("Send  (⌘↵)")
        self._save = QPushButton("Save plan")
        later = QPushButton("Later")
        self._send.clicked.connect(self._send_message)
        self._save.clicked.connect(self._save_plan)
        later.clicked.connect(self._later)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._send_message)  # ⌘↵ on macOS

        buttons = QHBoxLayout()
        buttons.addWidget(self._busy)
        buttons.addStretch()
        buttons.addWidget(later)
        buttons.addWidget(self._save)
        buttons.addWidget(self._send)
        layout = QVBoxLayout(self)
        layout.addWidget(self._log)
        layout.addWidget(self._input)
        layout.addLayout(buttons)
        self.resize(520, 480)

    def open(
        self,
        conversation: PlanningConversation,
        opening: str,
        on_save: Callable[[list[DraftTask]], None],
        on_later: Callable[[], None],
        can_save: bool = False,  # e.g. open tasks carried over: saving without adding is fine
    ) -> None:
        self._conversation, self._on_save, self._on_later = conversation, on_save, on_later
        self._log.clear()
        self._input.clear()
        self._say(opening)
        self._save.setEnabled(can_save)
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.center().x() - self.width() // 2, screen.top() + 60)
        self.show()
        self.raise_()
        self.activateWindow()
        self._input.setFocus()

    def _say(self, text: str, from_user: bool = False) -> None:
        body = html.escape(text).replace("\n", "<br>")
        who = "You" if from_user else "aiwa"
        color = "#2a78d6" if from_user else "#6b6a66"
        self._log.append(f'<p><b style="color:{color}">{who}</b><br>{body}</p>')

    def _send_message(self) -> None:
        text = self._input.toPlainText().strip()
        if not text or self._pending is not None or self._conversation is None:
            return
        self._say(text, from_user=True)
        self._input.clear()
        self._set_busy(True)
        self._pending = self._pool.submit(self._conversation.receive, text)
        self._poll.start()

    def _check_reply(self) -> None:
        if self._pending is None or not self._pending.done():
            return
        self._poll.stop()
        future, self._pending = self._pending, None
        self._set_busy(False)
        try:
            reply: Reply = future.result()
        except Exception as e:  # never lose the user's plan to an error
            self._say(f"Something went wrong ({e.__class__.__name__}). Please try again.")
            return
        for message in reply.messages:
            self._say(message)
        self._save.setEnabled(reply.done or self._save.isEnabled() and not self._conversation.asking)

    def _set_busy(self, busy: bool) -> None:
        self._busy.setText("thinking…" if busy else "")
        self._send.setEnabled(not busy)

    def _save_plan(self) -> None:
        self.hide()
        if self._on_save and self._conversation:
            self._on_save(list(self._conversation.accepted))

    def _later(self) -> None:
        self.hide()
        if self._on_later:
            self._on_later()
