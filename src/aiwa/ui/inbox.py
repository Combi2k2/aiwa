from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from aiwa.core.store import Store


class Inbox(QWidget):
    """Parking place for small tasks, to be cleared in one batch later."""

    def __init__(self, store: Store):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)  # see ui/popup.py
        self.setWindowTitle("aiwa: small tasks")
        self._store = store
        self._input = QLineEdit(placeholderText="Add a small task and press Enter")
        self._input.returnPressed.connect(self._add)
        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self._complete)
        layout = QVBoxLayout(self)
        layout.addWidget(self._input)
        layout.addWidget(self._list)
        layout.addWidget(QLabel("Double-click a task when it's done."))
        self.resize(380, 320)

    def open(self) -> None:
        self._refresh()
        self.show()
        self.raise_()
        self._input.setFocus()

    def _add(self) -> None:
        text = self._input.text().strip()
        if text:
            self._store.add_task(text, datetime.now(timezone.utc))
            self._input.clear()
            self._refresh()

    def _complete(self, item: QListWidgetItem) -> None:
        self._store.complete_task(item.data(Qt.ItemDataRole.UserRole), datetime.now(timezone.utc))
        self._refresh()

    def _refresh(self) -> None:
        self._list.clear()
        for task_id, text in self._store.open_tasks():
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, task_id)
            self._list.addItem(item)
