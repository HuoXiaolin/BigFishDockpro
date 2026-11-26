"""Assign enabled compact items to three horizontal zones, then order each zone."""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QDrag, QPainter, QPalette
from PyQt5.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QLabel,
                             QListWidget, QListWidgetItem, QVBoxLayout)

from capsule_order import ZONES
from ui_style import ModernComboBox, button


class ZoneList(QListWidget):
    def __init__(self, editor, zone):
        super().__init__(editor)
        self.editor = editor
        self.zone = zone
        self.setAccessibleName(ZONES[zone])
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDragDropOverwriteMode(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTextElideMode(Qt.ElideRight)

    def startDrag(self, actions):
        if not self.selectedItems():
            return
        drag = QDrag(self)
        drag.setMimeData(self.model().mimeData(self.selectedIndexes()))
        drag.exec_(Qt.MoveAction)
        drag.deleteLater()

    def dragEnterEvent(self, event):
        if event.source() in self.editor.lists.values():
            super().dragEnterEvent(event)
        else:
            event.ignore()

    def dropEvent(self, event):
        source = event.source()
        if source not in self.editor.lists.values() or not source.selectedItems():
            event.ignore()
            return
        target = self.itemAt(event.pos())
        row = self.row(target) + int(event.pos().y() > self.visualItemRect(target).center().y()) if target else self.count()
        self.editor.move_item(source, self, row)
        event.setDropAction(Qt.MoveAction)
        event.accept()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.count():
            painter = QPainter(self.viewport())
            painter.setPen(self.palette().color(QPalette.PlaceholderText))
            painter.drawText(self.viewport().rect(), Qt.AlignCenter, '拖到这里')


class CompactOrderDialog(QDialog):
    def __init__(self, parent, names, zones):
        super().__init__(parent)
        self.setWindowTitle('显示顺序')
        self.resize(650, 386)
        self.lists = {}
        self.active = None
        layout = QVBoxLayout(self)
        hint = QLabel('跨栏拖动可分配位置，栏内从上到下对应从左到右。中间栏整体对准胶囊中心，两侧空间不足时分页。' if names else '尚未开启收起显示项目。')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        columns = QHBoxLayout()
        layout.addLayout(columns, 1)
        for zone, title in ZONES.items():
            column = QVBoxLayout()
            header = QLabel(title)
            font = header.font()
            font.setBold(True)
            header.setFont(font)
            column.addWidget(header)
            view = self.lists[zone] = ZoneList(self, zone)
            column.addWidget(view, 1)
            columns.addLayout(column, 1)
            for key, label in names.items():
                if zones[key] == zone:
                    row = QListWidgetItem(label, view)
                    row.setData(Qt.UserRole, key)
                    row.setToolTip(label)
            view.itemSelectionChanged.connect(lambda v=view: self.selection_changed(v))
        controls = QHBoxLayout()
        layout.addLayout(controls)
        self.up = button('上移', lambda: self.shift(-1))
        self.down = button('下移', lambda: self.shift(1))
        controls.addWidget(self.up)
        controls.addWidget(self.down)
        controls.addSpacing(5)
        controls.addWidget(QLabel('位置'))
        self.location = ModernComboBox()
        self.location.setAccessibleName('所选项目的位置')
        for zone, title in ZONES.items():
            self.location.addItem(title, zone)
        self.location.activated[int].connect(self.assign)
        controls.addWidget(self.location)
        controls.addStretch()
        controls.addWidget(button('取消', self.reject))
        controls.addWidget(button('确定', self.accept, 'primary'))
        for view in self.lists.values():
            if view.count():
                view.setCurrentRow(0)
                break
        self.sync_controls()

    def selection_changed(self, view):
        if view.selectedItems():
            self.active = view
            for other in self.lists.values():
                if other is not view:
                    other.clearSelection()
        elif self.active is view:
            self.active = None
        self.sync_controls()

    def sync_controls(self):
        view = self.active
        self.up.setEnabled(view is not None and view.currentRow() > 0)
        self.down.setEnabled(view is not None and view.currentRow() < view.count()-1)
        self.location.setEnabled(view is not None)
        self.location.setCurrentIndex(self.location.findData(view.zone) if view is not None else -1)

    def move_item(self, source, target, insertion):
        row = source.currentRow()
        if row < 0:
            return
        if source is target and row < insertion:
            insertion -= 1
        item = source.takeItem(row)
        target.insertItem(insertion, item)
        target.setCurrentItem(item)
        target.scrollToItem(item)
        target.setFocus()
        self.sync_controls()

    def assign(self, index):
        target = self.lists[self.location.itemData(index)]
        if self.active is not None and self.active is not target:
            self.move_item(self.active, target, target.count())

    def shift(self, delta):
        view = self.active
        if view is not None and 0 <= view.currentRow()+delta < view.count():
            self.move_item(view, view, view.currentRow() + (2 if delta>0 else -1))

    def groups(self):
        return {zone:[view.item(i).data(Qt.UserRole) for i in range(view.count())]
                for zone, view in self.lists.items()}
