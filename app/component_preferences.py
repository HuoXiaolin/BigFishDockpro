"""Component settings backed by the same fields as the main settings dialog."""
import re

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLineEdit, QSpinBox, QVBoxLayout

from component_settings import ComponentPages, settings_footer
from settings_catalog import field_catalog
from settings_field_editors import SettingsFieldEditors
from ui_style import SettingsHeader, button, compact_dialog, exec_dialog, label


COMPONENTS = {
    'flash': ('闪念胶囊', (
        ('停靠与收起', 'position', ('enabled', 'side', 'edge_hide', 'auto_hide', 'delay', 'drop')),
        ('材质与配色', 'palette', ('appearance_source', 'backdrop_mode', 'palette', 'color')))),
    'spectrum': ('桌面音乐频谱', (
        ('显示与层级', 'wave', ('enabled', 'style', 'layer', 'locked')),
        ('材质与配色', 'palette', ('appearance_source', 'backdrop_mode', 'color_mode', 'mono_color')))),
    'daily_picture': ('每日图片', (
        ('图片与轮播', 'calendar', ('enabled', 'source', 'interval', 'locked')),
        ('材质与配色', 'palette', ('appearance_source', 'material', 'color')))),
    'watermark': ('桌面文字水印', (
        ('文字与颜色', 'notes', ('enabled', 'text', 'color', 'size', 'opacity')),
        ('位置与平铺', 'position', ('mode', 'position', 'angle', 'density', 'layer')))),
    'note': ('新便签默认设置', (
        ('材质与配色', 'palette', ('appearance_source', 'style')),)),
}


class ComponentPreferences(SettingsFieldEditors, QDialog):
    def __init__(self, runtime, component, page=0):
        super().__init__(runtime.dock, Qt.Window | Qt.FramelessWindowHint | Qt.WindowMinimizeButtonHint)
        self.runtime = runtime
        self.component = component
        title, pages = COMPONENTS[component]
        cfg = runtime.dock.cfg
        self.catalog = field_catalog(runtime.api, cfg)
        self.fields = {}
        self.baseline = {}
        self.local_paths = list(cfg['daily_picture_local_paths']) if component == 'daily_picture' else None
        self.setWindowTitle(title + ' · 大肥鱼Dock')
        self.resize(690, 470)
        body = QVBoxLayout(self)
        body.addWidget(SettingsHeader(self, title))
        self.tabs = ComponentPages(self, body, title)
        for name, icon, keys in pages:
            form = self.tabs.form(name, icon, name)
            for suffix in keys:
                key = component + '_' + suffix
                if suffix == 'locked':
                    self.catalog[key] = (None, '锁定位置与大小', 'check', None)
                self.add_field(form, key)
                field = self.fields[key]
                value = cfg[key]
                if isinstance(field, QComboBox):
                    field.setCurrentIndex(max(0, field.findData(value)))
                elif isinstance(field, QSpinBox):
                    field.setValue(value)
                elif isinstance(field, QLineEdit):
                    field.setText(value)
                else:
                    field.setChecked(value)
                self.baseline[key] = self.field_value(key, field)
            if component == 'daily_picture' and 'source' in keys:
                self.baseline['daily_picture_local_paths'] = list(self.local_paths)
                row = QHBoxLayout()
                row.addWidget(button('选择图片…', lambda: self.choose_paths(False)))
                row.addWidget(button('选择文件夹…', lambda: self.choose_paths(True)))
                form.addRow('本地图片', row)
                self.path_count = label('', 'muted')
                form.addRow(self.path_count)
                self.show_path_count()
        if component == 'watermark':
            from feature_config import WATERMARK_TEXT_LIMIT
            self.fields['watermark_text'].setMaxLength(WATERMARK_TEXT_LIMIT)
            self.fields['watermark_mode'].currentIndexChanged.connect(self.sync_watermark_fields)
            self.sync_watermark_fields()
        for key, field in self.fields.items():
            if key.endswith('_appearance_source') or key == 'spectrum_color_mode':
                field.currentIndexChanged.connect(self.sync_appearance_sources)
        self.sync_appearance_sources()
        self.status = label('', 'muted')
        settings_footer(self, body, self.status, self.commit)
        self.tabs.setCurrentIndex(page)
        compact_dialog(self)

    def choose_paths(self, folder):
        from daily_picture_card import pick_local_paths
        paths = pick_local_paths(self, folder)
        if paths:
            self.local_paths = paths
            source = self.fields['daily_picture_source']
            source.setCurrentIndex(source.findData('local'))
            self.show_path_count()

    def show_path_count(self):
        self.path_count.setText(f'已选择 {len(self.local_paths)} 个图片或文件夹')
        self.path_count.setToolTip('\n'.join(self.local_paths))

    def commit(self):
        from settings_effects import save_changes
        values = {key: self.field_value(key, f) for key, f in self.fields.items()}
        if self.local_paths is not None:
            values['daily_picture_local_paths'] = self.local_paths
        for key in self.fields:
            if self.catalog[key][2] == 'color':
                if values[key] and not re.fullmatch(r'#[0-9a-fA-F]{6}', values[key]):
                    self.status.setText('颜色请使用 #RRGGBB，或留空使用默认色。')
                    self.fields[key].setFocus()
                    return False
                values[key] = values[key].lower() or ('#ffffff' if key == 'watermark_color' else '')
        changes = {k: v for k, v in values.items() if self.baseline[k] != v}
        if not save_changes(self.runtime.tray, self.runtime.api, changes):
            self.status.setText('保存失败，请重试。')
            return False
        self.baseline.update(changes)
        self.status.setText('已保存。')
        return True


def open_preferences(runtime, component, page=0):
    exec_dialog(ComponentPreferences(runtime, component, page))
