"""Edit one pinned Dock entry without changing the underlying shortcut/file."""
import copy
import os
from urllib.parse import urlsplit
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QHBoxLayout, QLineEdit, QFileDialog, QLabel
from ui_style import SettingsHeader, label, button
from app_catalog import path_key, SHELL_TOOLS


class IconSettings(QDialog):
    def __init__(self, dock, index):
        super().__init__(dock, Qt.Window | Qt.FramelessWindowHint | Qt.WindowMinimizeButtonHint)
        self.setProperty('compactDialog', True)
        self.dock, self.index = dock, index
        self.original = copy.deepcopy(dock.cfg['items'][index])
        self.setWindowTitle('图标设置 · 大肥鱼Dock')
        self.setMinimumWidth(520)
        self.resize(620, 330)
        body = QVBoxLayout(self)
        body.setContentsMargins(18, 12, 18, 16)
        self.header = SettingsHeader(self, '图标设置')
        body.addWidget(self.header)
        body.addWidget(label('自定义此入口的名称、图标与启动链接。', 'muted'))
        form = QFormLayout()
        form.setVerticalSpacing(10)
        self.name = QLineEdit(self.original.get('name', ''))
        self.path = QLineEdit(self.original['path'])
        self.icon = QLineEdit(self.original.get('icon', ''))
        self.icon.setPlaceholderText('留空使用应用原图标')
        for field in (self.name, self.path, self.icon): field.setCursorPosition(0)
        for title, field in [('名称', self.name), ('启动链接', self.path), ('图标文件', self.icon)]:
            field.setAccessibleName(title)
            row = QHBoxLayout()
            row.addWidget(field, 1)
            if field is not self.name:
                row.addWidget(button('选择', lambda checked=False, target=field: self.choose(target)))
            if field is self.path: row.addWidget(button('文件夹', self.choose_folder))
            if field is self.icon: row.addWidget(button('默认', self.icon.clear))
            form.addRow(title, row)
        body.addLayout(form)
        preview = QHBoxLayout()
        self.preview = QLabel()
        self.preview.setFixedSize(44, 44)
        preview.addWidget(self.preview)
        preview.addWidget(label('支持程序、快捷方式、文件夹、网页或 Windows 应用链接。', 'muted'), 1)
        body.addLayout(preview)
        self.status = label('关闭会放弃尚未保存的修改。', 'muted')
        body.addWidget(self.status)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(button('关闭', self.reject))
        actions.addWidget(button('保存设置', self.commit, 'primary'))
        body.addLayout(actions)
        self.icon.textChanged.connect(self.refresh_preview)
        self.path.editingFinished.connect(self.refresh_preview)
        self.refresh_preview()

    def refresh_preview(self):
        custom = self.icon.text().strip()
        self.preview.setPixmap(self.dock.icons.get(custom or self.path.text().strip(), 88, bool(custom)).scaled(40,40,Qt.KeepAspectRatio,Qt.SmoothTransformation))

    def choose(self, field):
        filters = '图标或图片 (*.ico *.png *.jpg *.jpeg *.bmp *.webp *.exe *.dll *.lnk)' if field is self.icon else '所有文件 (*)'
        path, _ = QFileDialog.getOpenFileName(self, '选择图标' if field is self.icon else '选择启动目标', '', filters)
        if path: field.setText(path)

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, '选择启动文件夹')
        if path: self.path.setText(path)

    def commit(self):
        name, path, icon = self.name.text().strip(), self.path.text().strip().strip('"'), self.icon.text().strip().strip('"')
        if not name or not path:
            self.status.setText('请填写名称和启动链接。'); return
        try: url = urlsplit(path)
        except ValueError:
            self.status.setText('链接格式无效，请检查后重试。'); return
        remote = url.scheme.lower() in ('http', 'https') and bool(url.netloc)
        store = (path.lower().startswith('shell:appsfolder\\') and bool(path[17:].strip())) or path.casefold() in {value for _,_,value in SHELL_TOOLS}
        if not (remote or store or os.path.exists(path)):
            self.status.setText('启动目标不存在，请选择文件、文件夹或填写有效链接。'); return
        if icon and (not os.path.isfile(icon) or QPixmap(icon).isNull() and not icon.lower().endswith(('.ico','.exe','.dll','.lnk'))):
            self.status.setText('图标文件不可用，请重新选择。'); return
        items = copy.deepcopy(self.dock.cfg['items'])
        if self.index >= len(items) or items[self.index] != self.original:
            self.status.setText('此入口已在其他页面变更，请关闭后重新打开。'); return
        if any(i != self.index and item.get('path') and path_key(item['path']) == path_key(path) for i,item in enumerate(items)):
            self.status.setText('该链接已存在于 Dock，请使用其他链接。'); return
        candidate = dict(self.original, name=name, path=path)
        if icon: candidate['icon'] = os.path.abspath(icon)
        else: candidate.pop('icon', None)
        items[self.index] = candidate
        if not self.dock.tray.importer.apply_items(items):
            self.status.setText('保存失败，调整已保留，可重试。'); return
        self.original = copy.deepcopy(candidate)
        self.status.setText('图标设置已保存并生效，可继续调整。')
        self.refresh_preview()
