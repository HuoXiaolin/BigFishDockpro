from ui_style import compact_dialog
"""Panel group switches, merged navigation and non-exclusive file format rules."""
import copy
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLineEdit,QListWidget,QListWidgetItem,QInputDialog,QMessageBox
from ui_style import SettingsHeader,ModernCheckBox,ModernComboBox,label,button
from desktop_catalog import CATEGORIES,parse_extensions


class PanelDefinition(QDialog):
    def __init__(self, model=None, parent=None):
        super().__init__(parent,Qt.Dialog|Qt.FramelessWindowHint)
        self.setProperty('compactDialog',True)
        self.setWindowTitle('面板名称与格式')
        self.resize(480,320)
        self.setMinimumWidth(440)
        body=QVBoxLayout(self);body.setContentsMargins(18,14,18,16);body.setSpacing(12)
        body.addWidget(SettingsHeader(self,'编辑面板' if model else '新建面板'))
        form=QFormLayout();form.setVerticalSpacing(12)
        self.name=QLineEdit((model or {}).get('name',''))
        self.name.setMaxLength(40)
        self.formats=QLineEdit(' '.join((model or {}).get('extensions',[])))
        self.formats.setPlaceholderText('.pdf .docx .png，留空仅手动收纳')
        form.addRow('面板名称',self.name);form.addRow('自动归入格式',self.formats);body.addLayout(form)
        body.addWidget(label('格式规则作用于桌面内容，也识别快捷方式目标格式。同一文件可以同时出现在默认分组和多个自定义面板中，原文件保持原位。','muted'))
        self.status=label('','muted');body.addWidget(self.status)
        actions=QHBoxLayout();actions.addStretch();actions.addWidget(button('取消',self.reject));actions.addWidget(button('确定',self.validate,'primary'));body.addLayout(actions)

        compact_dialog(self)

    def extensions(self): return parse_extensions(self.formats.text())

    def validate(self):
        if not self.name.text().strip(): self.status.setText('请填写面板名称。');return
        try:self.extensions()
        except ValueError as error:self.status.setText(str(error));return
        self.accept()



from panel_group_view import GroupDialog
