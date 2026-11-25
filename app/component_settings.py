"""Navigation, grouped forms and a persistent footer for component settings."""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QFormLayout, QFrame, QHBoxLayout, QLabel, QScrollArea,
                             QStackedWidget, QVBoxLayout, QWidget)

from settings_design import SettingsNavigation
from ui_style import button


def section(parent, title):
    box = QWidget()
    box.setObjectName('SettingsGroup')
    box.setAttribute(Qt.WA_StyledBackground)
    layout = QVBoxLayout(box)
    layout.setContentsMargins(12, 9, 12, 10)
    layout.setSpacing(7)
    heading = QLabel(title)
    heading.setProperty('role', 'group-title')
    layout.addWidget(heading)
    parent.addWidget(box)
    return layout


class ComponentPages(QStackedWidget):
    def __init__(self, dialog, body, group):
        super().__init__()
        dialog.setProperty('simpleForms', True)
        content = QHBoxLayout()
        content.setSpacing(10)
        body.addLayout(content, 1)
        self.nav = SettingsNavigation()
        self.nav.setAccessibleName(group + '设置分类')
        self.nav.add_group(group)
        content.addWidget(self.nav)
        self.right = QVBoxLayout()
        content.addLayout(self.right, 1)
        self.right.addWidget(self, 1)
        self.entries = []
        self.nav.currentItemChanged.connect(self.navigate)
        self.currentChanged.connect(self.select_page)

    def navigate(self, item, previous):
        if item is not None and item.data(Qt.UserRole) is not None:
            self.setCurrentIndex(item.data(Qt.UserRole))

    def select_page(self, index):
        if 0 <= index < len(self.entries):
            self.nav.setCurrentItem(self.entries[index])

    def tabText(self, index):
        return self.entries[index].text()

    def page(self, title, icon):
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        part = QWidget()
        layout = QVBoxLayout(part)
        layout.setContentsMargins(1, 1, 6, 1)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(part)
        self.entries.append(self.nav.add_page(title, icon, self.count()))
        self.addWidget(scroll)
        return layout

    def form(self, title, icon, heading):
        layout = section(self.page(title, icon), heading)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(6)
        layout.addLayout(form)
        return form


def settings_footer(dialog, body, status, commit):
    row = QHBoxLayout()
    status.setWordWrap(True)
    row.addWidget(status, 1)
    row.addWidget(button('关闭', dialog.reject))
    save = button('保存设置', commit, 'primary')
    row.addWidget(save)
    body.addLayout(row)
    return save
