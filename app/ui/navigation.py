from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.navigation import navigation_group


class SidebarNavigation(QWidget):
    """Compact grouped replacement for an overcrowded top-level QTabWidget."""

    currentChanged = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._labels: list[str] = []
        self._groups: dict[str, QTreeWidgetItem] = {}
        self._items: list[QTreeWidgetItem] = []

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(210)
        self.tree.setMaximumWidth(270)
        self.tree.setIndentation(14)
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)

        self.title = QLabel("Chat")
        title_font = QFont(self.title.font())
        title_font.setPointSize(max(title_font.pointSize() + 2, 12))
        title_font.setBold(True)
        self.title.setFont(title_font)

        self.stack = QStackedWidget()

        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(12, 8, 8, 8)
        content_layout.addWidget(self.title)
        content_layout.addWidget(self.stack, 1)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.tree)

        content = QWidget()
        content.setLayout(content_layout)
        layout.addWidget(content, 1)

        self.tree.currentItemChanged.connect(self._current_item_changed)

    def _group_item(self, group: str) -> QTreeWidgetItem:
        item = self._groups.get(group)
        if item is not None:
            return item
        item = QTreeWidgetItem([group])
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        font = QFont(item.font(0))
        font.setBold(True)
        item.setFont(0, font)
        self.tree.addTopLevelItem(item)
        item.setExpanded(True)
        self._groups[group] = item
        return item

    def addTab(self, widget: QWidget, label: str) -> int:  # noqa: N802 - compatibility API
        index = self.stack.addWidget(widget)
        clean = label.strip() or f"Seite {index + 1}"
        self._labels.append(clean)

        group = navigation_group(clean)
        parent = self._group_item(group)
        item = QTreeWidgetItem([clean])
        item.setData(0, Qt.ItemDataRole.UserRole, index)
        parent.addChild(item)
        self._items.append(item)

        if index == 0:
            self.tree.setCurrentItem(item)
            self.title.setText(clean)
            self.stack.setCurrentIndex(index)
        return index

    def _current_item_changed(
        self,
        current: QTreeWidgetItem | None,
        _previous: QTreeWidgetItem | None,
    ) -> None:
        if current is None:
            return
        raw_index = current.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(raw_index, int):
            return
        if raw_index < 0 or raw_index >= self.stack.count():
            return
        self.stack.setCurrentIndex(raw_index)
        self.title.setText(self._labels[raw_index])
        self.currentChanged.emit(raw_index)

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802 - compatibility API
        if index < 0 or index >= len(self._items):
            return
        self.tree.setCurrentItem(self._items[index])

    def setCurrentWidget(self, widget: QWidget) -> None:  # noqa: N802 - compatibility API
        index = self.stack.indexOf(widget)
        if index >= 0:
            self.setCurrentIndex(index)

    def currentIndex(self) -> int:  # noqa: N802 - compatibility API
        return self.stack.currentIndex()

    def currentWidget(self) -> QWidget | None:  # noqa: N802 - compatibility API
        return self.stack.currentWidget()

    def widget(self, index: int) -> QWidget | None:
        return self.stack.widget(index)

    def indexOf(self, widget: QWidget) -> int:  # noqa: N802 - compatibility API
        return self.stack.indexOf(widget)

    def count(self) -> int:
        return self.stack.count()

    def label(self, index: int) -> str:
        if index < 0 or index >= len(self._labels):
            return ""
        return self._labels[index]
