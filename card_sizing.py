"""One settings page for the dimensions and fonts of every desktop card."""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QApplication
from ui_style import SettingsHeader,label,button,ModernSpinBox,compact_dialog
from screen_layout import screen_records
from card_metrics import metrics


class CardSizingDialog(QDialog):
    def __init__(self,runtime,kind=None,identity=None):
        super().__init__(None,Qt.Window|Qt.FramelessWindowHint|Qt.WindowMinimizeButtonHint)
        self.runtime=runtime
        self.setWindowTitle('统一卡片尺寸与文字 · 大肥鱼Dock');self.resize(620,380);self.setMinimumSize(520,330)
        body=QVBoxLayout(self);body.addWidget(SettingsHeader(self,'统一卡片尺寸与文字'))
        body.addWidget(label('所有桌面卡片与便签共用设置，新建卡片也会自动沿用。','muted'))
        form=QFormLayout();form.setVerticalSpacing(10);body.addLayout(form)
        self.width_field=ModernSpinBox();self.width_field.setRange(160,8192)
        self.height_field=ModernSpinBox();self.height_field.setRange(96,8192)
        self.text_field=ModernSpinBox();self.text_field.setRange(8,48)
        form.addRow('统一宽度（像素）',self.width_field);form.addRow('统一高度（像素）',self.height_field);form.addRow('统一文字大小（像素）',self.text_field)
        body.addWidget(label('一次保存应用到全部卡片和便签；位置、内容、颜色与收起状态分别保留。宽高指展开尺寸，内容超出时滚动。换屏按比例适配，尺寸统一在此调整。','muted'))
        self.status=label('修改后点击保存；关闭放弃尚未保存的改动。','muted');body.addWidget(self.status)
        actions=QHBoxLayout();actions.addStretch();actions.addWidget(button('关闭',self.reject));self.save_button=button('保存并应用到全部',self.commit,'primary');actions.addWidget(self.save_button);body.addLayout(actions)
        self.load();compact_dialog(self)
        from settings_layout import fit_auxiliary_dialog
        fit_auxiliary_dialog(self,runtime.dock.cfg)
    def reference(self):
        screen=QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        return screen
    def load(self):
        screen=self.reference();area=screen.availableGeometry()
        rect,factor,font=metrics(self.runtime.dock.cfg,list(area.getRect()),screen_records(),{'screen':screen.name(),'area':list(area.getRect())})
        self.width_field.setValue(rect[2]);self.height_field.setValue(rect[3]);self.text_field.setValue(min(48,font))
    def commit(self):
        if self.runtime.layout.pending:self.status.setText('屏幕正在调整，请稍后保存。');return False
        if not self.runtime.notes.flush():self.status.setText('请先保存便签正文后重试。');return False
        screen=self.reference();area=screen.availableGeometry();cfg=self.runtime.dock.cfg
        _,ui_factor,_=metrics(cfg,list(area.getRect()),screen_records(),{'screen':screen.name(),'area':list(area.getRect())})
        profile={'width':min(self.width_field.value(),area.width()),'height':min(self.height_field.value(),area.height()),'font_size':self.text_field.value(),'area':[area.width(),area.height()],'density':cfg.get('card_scale',70)/100,'ui_scale':ui_factor}
        candidate=dict(cfg,card_sizing=profile)
        try:
            if self.runtime.api.save_config(candidate) is False:raise OSError('configuration write failed')
        except (OSError,ValueError):self.status.setText('保存失败，所有卡片保持原设置。');return False
        cfg['card_sizing']=profile
        self.runtime.panels.reposition();self.runtime.panels.sync_windows();self.runtime.notes.reposition();self.runtime.notes.sync()
        self.load();self.status.setText('已统一应用到所有桌面卡片和便签，新建卡片自动沿用。');return True
