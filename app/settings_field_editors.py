"""Field editors and dependencies shared by the main and component settings."""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QColorDialog, QComboBox, QHBoxLayout, QLineEdit, QSpinBox, QVBoxLayout, QWidget

from ui_style import ModernCheckBox, ModernComboBox, ModernSpinBox, ThemeSwatches, button, label


class SettingsFieldEditors:
    @staticmethod
    def field_value(key, field):
        if isinstance(field, QComboBox):
            return field.currentData()
        if isinstance(field, QSpinBox):
            return 100 - field.value() if key == 'transparency' else field.value()
        if isinstance(field, QLineEdit):
            return field.text().strip()
        return field.isChecked()

    def add_field(self, form, key, visible=True):
        _, title, kind, options = self.catalog[key]
        if kind == 'combo':
            self.combo(form, key, title, options, visible=visible)
        elif kind == 'number':
            self.number(form, key, title, *options)
        else:
            getattr(self, kind)(form, key, title)

    def sync_appearance_sources(self, *args):
        for source, keys in (
                ('panel_appearance_source', ('panel_material', 'panel_theme', 'panel_color', 'panel_highlight', 'panel_opacity', 'panel_blur')),
                ('daily_picture_appearance_source', ('daily_picture_material', 'daily_picture_color')),
                ('spectrum_appearance_source', ('spectrum_color_mode', 'spectrum_mono_color')),
                ('flash_appearance_source', ('flash_palette',)),
                ('note_appearance_source', ('note_style',))):
            if source not in self.fields:
                continue
            custom = self.fields[source].currentData() == 'custom'
            for key in keys:
                field = self.fields.get(key)
                if field is not None:
                    enabled = custom and (key != 'spectrum_mono_color' or self.fields['spectrum_color_mode'].currentData() == 'mono')
                    (field.parentWidget() if key.endswith('_color') else field).setEnabled(enabled)
            if source == 'panel_appearance_source' and 'panel_preset' in self.__dict__:
                self.panel_preset.setEnabled(custom)

    def sync_watermark_fields(self):
        tiled = self.fields['watermark_mode'].currentData() == 'tile'
        self.fields['watermark_position'].setEnabled(not tiled)
        self.fields['watermark_density'].setEnabled(tiled)

    def field_label(self, title):
        widget = label(title)
        widget.setFixedWidth(130)
        widget.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        return widget

    def combo(self, form, key, title, options, visible=True):
        field = ModernComboBox(form.parentWidget())
        for name, value in options:
            field.addItem(name, value)
            if key == 'spectrum_color_mode' and value != 'mono':
                from spectrum_effects import palette_icon
                field.setItemIcon(field.count()-1,palette_icon(value))
        field.setAccessibleName(title)
        self.fields[key] = field
        if visible:form.addRow(self.field_label(title), field)
        else:field.hide()

    def number(self, form, key, title, lower, upper):
        field = ModernSpinBox()
        field.setRange(lower, upper)
        field.setAccessibleName(title)
        self.fields[key] = field
        form.addRow(self.field_label(title), field)

    def text(self, form, key, title):
        field = QLineEdit()
        field.setAccessibleName(title)
        self.fields[key] = field
        form.addRow(self.field_label(title), field)

    def color(self, form, key, title):
        wrapper = QWidget()
        container = QVBoxLayout(wrapper)
        container.setContentsMargins(0, 0, 0, 0)
        container.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(8)
        field = QLineEdit()
        field.setPlaceholderText('默认色 / #RRGGBB')
        field.setAccessibleName(title)
        self.fields[key] = field
        row.addWidget(field, 1)
        def choose():
            value = QColorDialog.getColor(QColor(field.text() or '#b8d9ef'), self, title)
            if value.isValid(): field.setText(value.name())
        row.addWidget(button('选择', choose))
        row.addWidget(button('默认', field.clear))
        container.addLayout(row)
        container.addWidget(ThemeSwatches(field))
        form.addRow(self.field_label(title), wrapper)

    def check(self, form, key, title):
        field = ModernCheckBox(title)
        self.fields[key] = field
        form.addRow('', field)
