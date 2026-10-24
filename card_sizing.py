"""Explicit size and text controls for collection and sticky-note cards."""
import copy
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QApplication
from ui_style import SettingsHeader,label,button,ModernComboBox,ModernSpinBox,ModernCheckBox,compact_dialog
from screen_layout import capture,screen_records


class CardSizingDialog(QDialog):
    def __init__(self,runtime,kind=None,identity=None):
        super().__init__(None,Qt.Window|Qt.FramelessWindowHint|Qt.WindowMinimizeButtonHint)
        self.runtime=runtime;self.loading=True
        self.setWindowTitle('卡片尺寸与文字 · 大肥鱼Dock');self.resize(620,450);self.setMinimumSize(520,380)
        body=QVBoxLayout(self);body.addWidget(SettingsHeader(self,'卡片尺寸与文字'))
        form=QFormLayout();form.setVerticalSpacing(10);body.addLayout(form)
        self.target=ModernComboBox()
        for model in runtime.dock.cfg['desktop_panels']:self.target.addItem('桌面卡片 · '+model['name'],('panel',model['id']))
        for row in runtime.notes.rows():self.target.addItem('便签 · '+row['title'],('note',row['id']))
        form.addRow('选择卡片',self.target)
        self.width_field=ModernSpinBox();self.width_field.setRange(160,8192)
        self.height_field=ModernSpinBox();self.height_field.setRange(96,8192)
        self.text_field=ModernSpinBox();self.text_field.setRange(8,48)
        form.addRow('宽度（像素）',self.width_field);form.addRow('高度（像素）',self.height_field);form.addRow('文字大小（像素）',self.text_field)
        self.auto_height=ModernCheckBox('按内容自动调整高度');form.addRow(self.auto_height)
        body.addWidget(label('数值对应当前屏幕界面尺寸。换屏后按比例适配，手动调整会建立新的参照。合并卡片共用宽高，文字大小独立；锁定状态仍会保留。','muted'))
        self.status=label('修改后点击保存；关闭放弃尚未保存的改动。','muted');body.addWidget(self.status)
        actions=QHBoxLayout();actions.addStretch();actions.addWidget(button('关闭',self.reject));self.save_button=button('保存设置',self.commit,'primary');actions.addWidget(self.save_button);body.addLayout(actions)
        self.auto_height.toggled.connect(lambda checked:self.height_field.setEnabled(not checked))
        self.height_field.valueChanged.connect(self.height_changed)
        self.target.currentIndexChanged.connect(self.load)
        selected=next((index for index in range(self.target.count()) if tuple(self.target.itemData(index))==(kind,identity)),0) if kind and identity else 0
        self.target.setCurrentIndex(max(0,selected));self.load();compact_dialog(self)
        from settings_layout import fit_auxiliary_dialog
        fit_auxiliary_dialog(self,runtime.dock.cfg)
    def height_changed(self):
        if not self.loading:self.auto_height.setChecked(False)
    def load(self,*args):
        self.loading=True;data=self.target.currentData();available=bool(data)
        self.save_button.setEnabled(available)
        for field in (self.width_field,self.height_field,self.text_field):field.setEnabled(available)
        if not available:self.status.setText('暂无卡片，请先创建桌面卡片或便签。');self.loading=False;return
        kind,identity=data
        if kind=='panel':
            window=self.runtime.panels.windows.get(identity)
            if not window:self.status.setText('请先启用桌面收纳，再调整卡片。');self.save_button.setEnabled(False);self.loading=False;return
            bounds=window.bounds();font=window.text_pixels();automatic=self.runtime.dock.cfg['merged_compact'] if self.runtime.panels.is_merged(identity) else window.model.get('compact',True)
            if not window.collapsed:bounds[2:]=[window.width(),window.height()]
            self.auto_height.setVisible(True);self.auto_height.setChecked(automatic)
        else:
            window=self.runtime.notes.windows.get(identity)
            if not window:self.status.setText('该便签尚未显示，请先从便签管理打开。');self.save_button.setEnabled(False);self.loading=False;return
            bounds=[window.x(),window.y(),window.width(),window.expanded_height if window.row()['collapsed'] else window.height()];font=window.text_pixels();automatic=False;self.auto_height.setVisible(False);self.auto_height.setChecked(False)
        self.width_field.setValue(bounds[2]);self.height_field.setValue(bounds[3]);self.height_field.setEnabled(not automatic);self.text_field.setValue(font);self.loading=False
    def commit(self):
        data=self.target.currentData()
        if not data:return False
        if self.runtime.layout.pending:self.status.setText('屏幕正在调整，请稍后保存。');return False
        kind,identity=data
        window=(self.runtime.panels.windows if kind=='panel' else self.runtime.notes.windows).get(identity)
        if not window:self.status.setText('卡片已关闭，请重新选择。');return False
        screen=QApplication.screenAt(window.frameGeometry().center()) or QApplication.primaryScreen();area=screen.availableGeometry()
        width=min(self.width_field.value(),area.width());height=min(self.height_field.value(),area.height())
        x=max(area.left(),min(window.x(),area.right()-width+1));y=max(area.top(),min(window.y(),area.bottom()-height+1));geometry=[x,y,width,height]
        font=self.text_field.value();factor=window.ui_factor
        if kind=='panel':
            manager=self.runtime.panels;models=copy.deepcopy(manager.cfg['desktop_panels'])
            next(model for model in models if model['id']==identity).update(geometry=geometry,font_size=font,font_scale=factor,compact=self.auto_height.isChecked())
            changes={'desktop_panels':models,'display_layout':self.runtime.layout.panel_update(identity,geometry)}
            if manager.is_merged(identity):changes.update(merged_geometry=geometry,merged_compact=self.auto_height.isChecked())
            if not manager.commit(**changes):self.status.setText('保存失败，原卡片尺寸与文字保持不变。');return False
            manager.reposition();manager.sync_windows()
            if self.auto_height.isChecked():window.fit_content()
        else:
            manager=self.runtime.notes
            if not manager.flush():self.status.setText('请先保存便签正文后重试。');return False
            manager.update(identity,geometry=geometry,layout=capture(geometry,screen_records(),factor,manager.runtime.dock.cfg.get('card_scale',70)/100),font_size=font,font_scale=factor)
            if not manager.flush():manager.pending.pop(identity,None);self.status.setText('保存失败，原便签尺寸与文字保持不变。');return False
            window.reposition();window.apply_style();manager.sync()
        self.load();self.status.setText('已保存，窗口保持打开，可继续调整。');return True
