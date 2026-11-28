"""Preview original pointer images and expose the same actions in both menus."""
import struct

from PyQt5.QtCore import Qt, QSignalBlocker
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from cursor_styles import PACK_ERRORS, read_pack
from settings_design import ResponsiveFields
from ui_style import ModernComboBox, button, label


PREVIEW_ROLES = (('Arrow', '普通'), ('Hand', '链接'), ('IBeam', '文本'),
                 ('AppStarting', '后台忙'), ('Wait', '等待'))


def chunks(data):
    offset = 0
    while offset + 8 <= len(data):
        kind, size = struct.unpack_from('<4sI', data, offset)
        end = offset + 8 + size
        if end > len(data):
            break
        yield kind, data[offset + 8:end]
        offset = end + (size & 1)


def pointer_image(data, size=32):
    """Decode one preview frame from the CUR or ANI without changing the file."""
    if data.startswith(b'RIFF') and data[8:12] == b'ACON':
        for kind, payload in chunks(data[12:]):
            if kind == b'LIST' and payload.startswith(b'fram'):
                data = next((frame for kind, frame in chunks(payload[4:]) if kind == b'icon'), b'')
                break
    if len(data) < 6:
        return QImage()
    reserved, kind, count = struct.unpack_from('<HHH', data)
    end = 6 + 16 * count
    if reserved or kind not in (1, 2) or end > len(data):
        return QImage()
    entries = struct.iter_unpack('<BBBBHHII', data[6:end])
    entries = sorted(entries, key=lambda entry: abs((entry[0] or 256) - size))
    for width, height, colors, _, _, _, length, offset in entries:
        if offset < end or offset + length > len(data):
            continue
        image_bytes = data[offset:offset + length]
        if image_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
            image = QImage.fromData(image_bytes, 'PNG')
        else:
            # ICO and CUR share a DIB layout. Only the directory differs.
            directory = struct.pack('<HHHBBBBHHII', 0, 1, 1, width, height, colors, 0,
                                    0, 0, length, 22)
            image = QImage.fromData(directory + image_bytes, 'ICO')
        if not image.isNull():
            return image.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return QImage()


class CursorStylePanel(QWidget):
    def __init__(self, service):
        super().__init__()
        self.service = service
        self.current = label('', 'muted')
        self.current.setTextFormat(Qt.PlainText)
        self.choices = ModernComboBox()
        self.choices.setAccessibleName('鼠标方案')
        self.apply_button = button('应用方案', self.apply_choice, 'primary')
        self.restore_button = button('恢复系统默认', lambda: self.apply_choice(restore=True))
        self.status = label('', 'muted')
        self.status.setTextFormat(Qt.PlainText)
        self.status.hide()

        body = QVBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(10)
        body.addWidget(self.current)
        selector = QHBoxLayout()
        selector.addWidget(self.choices, 1)
        selector.addWidget(button('导入方案…', self.import_choice))
        body.addLayout(selector)
        body.addWidget(label('指针预览', 'section'))
        self.previews = []
        previews = ResponsiveFields()
        previews.add(self.preview_surface('浅色背景', '#f6f8fc', '#1e2b38'))
        previews.add(self.preview_surface('深色背景', '#252e39', '#edf2f7'))
        body.addWidget(previews)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(self.restore_button)
        actions.addWidget(self.apply_button)
        body.addLayout(actions)
        body.addWidget(self.status)

        self.choices.currentIndexChanged.connect(self.preview_choice)
        self.service.changed.connect(self.refresh)
        self.refresh()

    def preview_surface(self, title, background, foreground):
        surface = QWidget()
        surface.setObjectName('CursorPreview')
        surface.setAttribute(Qt.WA_StyledBackground)
        surface.setStyleSheet(f'QWidget#CursorPreview {{background:{background};border-radius:8px;}}'
                              f'QWidget#CursorPreview QLabel {{color:{foreground};background:transparent;}}')
        layout = QVBoxLayout(surface)
        layout.setContentsMargins(8, 9, 8, 9)
        layout.setSpacing(6)
        layout.addWidget(label(title, 'muted'))
        row = QHBoxLayout()
        row.setSpacing(3)
        icons = []
        for _, name in PREVIEW_ROLES:
            column = QVBoxLayout()
            column.setSpacing(1)
            icon = QLabel(alignment=Qt.AlignCenter)
            icon.setMinimumHeight(32)
            caption = QLabel(name, alignment=Qt.AlignCenter)
            column.addWidget(icon)
            column.addWidget(caption)
            row.addLayout(column, 1)
            icons.append(icon)
        layout.addLayout(row)
        self.previews.append(icons)
        return surface

    def refresh(self):
        selected = self.choices.currentData()
        styles = self.service.styles()
        try:
            active, title = self.service.current(styles)
            self.current.setText('当前使用 · ' + title)
        except OSError:
            active = None
            self.current.setText('暂时无法读取 Windows 鼠标方案')
        with QSignalBlocker(self.choices):
            self.choices.clear()
            for style in styles:
                self.choices.addItem(style.title, style)
            selected = selected if selected in styles else active
            self.choices.setCurrentIndex(styles.index(selected) if selected in styles else 0)
        self.restore_button.setEnabled(self.service.system.enabled)
        self.preview_choice()

    def preview_choice(self):
        style = self.choices.currentData()
        mapping, files = {}, {}
        self.status.hide()
        if style is not None:
            try:
                _, mapping, files = read_pack(style.source)
            except PACK_ERRORS as error:
                self.report(str(error))
        self.apply_button.setEnabled(bool(mapping) and self.service.system.enabled)
        for index, (role, name) in enumerate(PREVIEW_ROLES):
            file = mapping.get(role, '')
            preview = QPixmap.fromImage(pointer_image(files.get(file, b'')))
            for icons in self.previews:
                icons[index].setPixmap(preview)
                icons[index].setToolTip(name + (' · 动态指针' if file.lower().endswith('.ani') else ''))

    def import_choice(self):
        start = str(self.service.local) if self.service.local.is_dir() else ''
        source, _ = QFileDialog.getOpenFileName(self, '导入鼠标方案', start, '鼠标方案 (*.inf pack.ini)')
        if not source:
            return
        try:
            style = self.service.import_style(source)
        except PACK_ERRORS as error:
            self.report('导入失败 · ' + str(error))
            return
        for index in range(self.choices.count()):
            if self.choices.itemData(index) == style:
                self.choices.setCurrentIndex(index)
                break
        self.report('方案已导入，点击「应用方案」使用。')

    def apply_choice(self, restore=False):
        try:
            name = self.service.apply(None if restore else self.choices.currentData())
        except PACK_ERRORS as error:
            self.report('应用失败 · ' + str(error))
            return
        self.report('已应用 · ' + name)

    def report(self, message):
        self.status.setText(message)
        self.status.show()


def add_tray_menu(menu, runtime):
    from settings_catalog import CURSORS
    from shell_menu import open_settings

    def cycle():
        try:
            runtime.cursor_styles.cycle()
        except PACK_ERRORS as error:
            runtime.tray.showMessage('鼠标样式应用失败', str(error), runtime.tray.icon(), 5000)

    def refresh():
        service = runtime.cursor_styles
        choices = service.styles()
        try:
            _, name = service.current(choices)
        except OSError:
            name = '读取失败'
        change.setText('切换鼠标样式 · ' + name)
        change.setEnabled(bool(choices) and service.system.enabled)

    change = menu.addAction('切换鼠标样式', cycle)
    menu.addAction('鼠标样式设置…', lambda: open_settings(runtime, CURSORS))
    menu.aboutToShow.connect(refresh)
