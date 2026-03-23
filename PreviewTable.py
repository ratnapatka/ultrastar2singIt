from __future__ import annotations

from PySide6 import QtCore
from PySide6.QtCore import Qt, QRect, Signal
from PySide6.QtGui import QPainter, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QStyle,
    QStyleOptionButton,
    QTableWidget,
)

import GuiElement


class CheckBoxHeader(QHeaderView):
    toggled = Signal(bool)

    def __init__(self, checkbox_section: int = 0, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.section = checkbox_section
        self.state = Qt.Unchecked
        self.setSectionsClickable(True)

    def set_check_state(self, state: Qt.CheckState) -> None:
        if state == self.state:
            return
        self.state = state
        self.viewport().update()

    def checkbox_rect(self) -> QRect:
        w = self.sectionSize(self.section)
        h = self.height()
        if w <= 0 or h <= 0:
            return QRect()

        opt = QStyleOptionButton()
        indicator = self.style().subElementRect(QStyle.SE_CheckBoxFocusRect, opt, self)
        x = (w - indicator.width()) // 2 #TODO: figure out the x location calculation so the checkbox is centered
        y = (h - indicator.height()) // 2
        return QRect(5, y, indicator.width(), indicator.height())

    def paintSection(self, painter: QPainter, rect: QRect, logicalIndex: int) -> None:
        painter.save()
        super().paintSection(painter, rect, logicalIndex)
        painter.restore()
        if logicalIndex != self.section:
            return

        cb_rect = self.checkbox_rect()
        if cb_rect.isNull():
            return

        opt = QStyleOptionButton()
        opt.rect = cb_rect
        opt.state = QStyle.State_Enabled
        if self.state == Qt.Checked:
            opt.state |= QStyle.State_On
        elif self.state == Qt.PartiallyChecked:
            opt.state |= QStyle.State_NoChange
        else:
            opt.state |= QStyle.State_Off

        self.style().drawControl(QStyle.CE_CheckBox, opt, painter)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.checkbox_rect().contains(event.pos()):
            new_checked = self.state != Qt.Checked
            self.state = Qt.Checked if new_checked else Qt.Unchecked
            self.viewport().update()
            self.toggled.emit(new_checked)
            event.accept()
            return
        super().mousePressEvent(event)


class PreviewTable(QTableWidget):
    checkboxStateChanged = Signal()

    def __init__(self, *args, checkbox_column: int = 0, **kwargs):
        super().__init__(*args, **kwargs)
        self.checkbox_column = checkbox_column

        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

        self.header = CheckBoxHeader(checkbox_section=self.checkbox_column, parent=self)
        self.setHorizontalHeader(self.header)
        self.header.toggled.connect(self.set_all_checkboxes)

        self.itemChanged.connect(self.sync_header_checkbox)
        self.itemChanged.connect(lambda *_: self.checkboxStateChanged.emit())

        self.setEditTriggers(QAbstractItemView.NoEditTriggers)

        self.setIconSize(QtCore.QSize(GuiElement.ICON_SIZE * 2, GuiElement.ICON_SIZE))
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.verticalHeader().setDefaultSectionSize(22)
        self.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setColumnCount(6)
        self.setHorizontalHeaderLabels(
            ["", "Song", "Video", "Audio", "Image", "Lyrics"])
        self.horizontalHeader().setFixedHeight(24)
        self.horizontalHeader().setMinimumSectionSize(10)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.setColumnWidth(0, 24)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for i in range(2, self.columnCount()):
            self.horizontalHeader().setSectionResizeMode(i, QHeaderView.Fixed)
            self.setColumnWidth(i, 40)

    def selected_rows(self) -> list[int]:
        sm = self.selectionModel()
        if sm is None:
            return []
        return sorted({idx.row() for idx in sm.selectedRows()})

    def toggle_rows(self, rows: list[int]) -> None:
        if not rows:
            return

        target = Qt.Checked if any(
            (it := self.item(r, self.checkbox_column)) is not None and it.checkState() != Qt.Checked
            for r in rows
        ) else Qt.Unchecked

        self.blockSignals(True)
        try:
            for r in rows:
                it = self.item(r, self.checkbox_column)
                if it is not None:
                    it.setCheckState(target)
        finally:
            self.blockSignals(False)

        self.sync_header_checkbox()
        self.checkboxStateChanged.emit()

    def set_all_checkboxes(self, checked: bool) -> None:
        target = Qt.Checked if checked else Qt.Unchecked

        self.blockSignals(True)
        try:
            for r in range(self.rowCount()):
                it = self.item(r, self.checkbox_column)
                if it is not None:
                    it.setCheckState(target)
        finally:
            self.blockSignals(False)

        self.header.set_check_state(target)
        self.checkboxStateChanged.emit()

    def sync_header_checkbox(self, *_args) -> None:
        checked = sum(
            1 for r in range(self.rowCount())
            if (it := self.item(r, self.checkbox_column)) is not None and it.checkState() == Qt.Checked
        )
        total = self.rowCount()

        if checked == 0 or total == 0:
            state = Qt.Unchecked
        elif checked == total:
            state = Qt.Checked
        else:
            state = Qt.PartiallyChecked

        self.header.set_check_state(state)

    def mousePressEvent(self, event) -> None:
        before = {idx.row() for idx in self.selectionModel().selectedRows()} if self.selectionModel() else set()
        super().mousePressEvent(event)
        after = {idx.row() for idx in self.selectionModel().selectedRows()} if self.selectionModel() else set()

        if after - before:
            self.toggle_rows(sorted(after))

    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.SelectAll):
            self.selectAll()
            self.toggle_rows(self.selected_rows())
            event.accept()
            return
        if event.key() == Qt.Key_Space:
            self.toggle_rows(self.selected_rows())
            event.accept()
            return
        super().keyPressEvent(event)