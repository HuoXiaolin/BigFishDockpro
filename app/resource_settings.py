"""Preferences shared by the desktop monitor and the independent taskbar readout."""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QWidget,QDialog,QTabWidget,QFrame,QLabel,QPushButton,QLineEdit,QColorDialog,QScrollArea,
                             QVBoxLayout,QHBoxLayout,QGridLayout,QFormLayout)
from appearance_presets import COLOR_MODES,material_choices
from resource_options import METRICS,TINTS,TASK_METRICS,background,clean_background
from ui_style import SettingsHeader,ModernComboBox,ModernSpinBox,ModernCheckBox,ColorSwatch,THEME_COLORS,button


class ResourceOptions(QDialog):
    def __init__(self,service):
        super().__init__(None,Qt.Window|Qt.FramelessWindowHint|Qt.WindowMinimizeButtonHint)
        self.service=service;cfg=service.cfg
        self.setWindowTitle('资源胶囊设置 · 大肥鱼Dock');self.resize(570,550)
        self.fields={};self.custom_fields={};self.task_fields={};self.tints=dict(cfg['resource_tints'])
        from copy import deepcopy
        self.baseline=deepcopy(cfg)
        box=QVBoxLayout(self);box.addWidget(SettingsHeader(self,'资源胶囊设置'))
        self.tabs=QTabWidget();box.addWidget(self.tabs,1)
        def page(name):
            scroll=QScrollArea();scroll.setFrameShape(QFrame.NoFrame);scroll.setWidgetResizable(True)
            part=QWidget();layout=QVBoxLayout(part);scroll.setWidget(part);self.tabs.addTab(scroll,name);return layout
        def combo(form,key,title,options,value,store):
            field=ModernComboBox()
            for label,data in options:field.addItem(label,data)
            field.setCurrentIndex(max(0,field.findData(value)));field.setAccessibleName(title)
            form.addRow(title,field);store[key]=field;return field
        def spin(form,key,title,low,high,value,store):
            field=ModernSpinBox();field.setRange(low,high);field.setValue(value);field.setAccessibleName(title)
            form.addRow(title,field);store[key]=field
        def check(title,on):
            field=ModernCheckBox(title);field.setChecked(on);return field

        desktop=page('桌面监控')
        for key,title in [('resource_enabled','显示资源胶囊'),('resource_auto_hide','鼠标离开后收起'),('resource_bt_tray','蓝牙电量托盘图标')]:
            self.fields[key]=check(title,cfg[key]);desktop.addWidget(self.fields[key])
        form=QFormLayout();desktop.addLayout(form)
        combo(form,'resource_layer','桌面层级',[('置顶','top'),('置底','bottom')],cfg['resource_layer'],self.fields)
        combo(form,'resource_fold','收起形态',[('胶囊','pill'),('圆球','ball'),('方条','bar')],cfg['resource_fold'],self.fields)
        combo(form,'resource_interval','采样间隔',[(str(s)+' 秒',s) for s in (1,2,5)],cfg['resource_interval'],self.fields)
        spin(form,'resource_delay','收起延迟（秒）',1,30,cfg['resource_delay'],self.fields)
        grid=QGridLayout();desktop.addLayout(grid)
        for i,(key,title) in enumerate(METRICS.items()):
            field=check(title,cfg['resource_'+key]);self.fields['resource_'+key]=field;grid.addWidget(field,i//3,i%3)
        from pawnio_setup import installed
        version=installed();driver=QHBoxLayout();desktop.addLayout(driver)
        driver.addWidget(QLabel('PawnIO '+version if version else 'PawnIO 未安装'));driver.addStretch()
        driver.addWidget(button('打开驱动安装程序',self.install_driver));desktop.addStretch()

        bar=page('任务栏监控')
        self.fields['resource_taskbar']=check('显示任务栏监控',cfg['resource_taskbar']);bar.addWidget(self.fields['resource_taskbar'])
        controls=QGridLayout();bar.addLayout(controls)
        for i,key in enumerate(TASK_METRICS):
            field=check(METRICS[key],key in cfg['resource_task_metrics']);self.task_fields[key]=field;controls.addWidget(field,i//3,i%3)
        bar.addStretch()

        style=page('背景与配色');style_form=QFormLayout();style.addLayout(style_form)
        source=combo(style_form,'resource_background','背景',[('跟随整体','global'),('单独设置','custom')],cfg['resource_background'],self.fields)
        self.custom_box=QWidget();custom=QFormLayout(self.custom_box);custom.setContentsMargins(0,0,0,0);style.addWidget(self.custom_box)
        saved=cfg['resource_appearance'] or background(cfg)
        combo(custom,'material','材质',material_choices(saved['material']),saved['material'],self.custom_fields)
        combo(custom,'theme','明暗模式',COLOR_MODES,saved['theme'],self.custom_fields)
        color_line=QHBoxLayout();self.color=QLineEdit(saved['color']);self.color.setPlaceholderText('#RRGGBB');self.color.setAccessibleName('背景主题色')
        color_line.addWidget(self.color,1);color_line.addWidget(button('选择',self.pick_background))
        color_line.addWidget(button('默认',self.color.clear));custom.addRow('主题色',color_line)
        chips=QHBoxLayout()
        for title,rgb in THEME_COLORS:chips.addWidget(ColorSwatch(self.color,title,rgb,self.custom_box))
        chips.addStretch();custom.addRow('',chips)
        for key,title,low,high in [('opacity','不透明度（%）',0,100),('blur','模糊强度',2,30),('highlight','高光（%）',0,100)]:
            spin(custom,key,title,low,high,saved[key],self.custom_fields)
        self.custom_box.setVisible(source.currentData()=='custom')
        source.currentIndexChanged.connect(lambda:self.custom_box.setVisible(source.currentData()=='custom'))
        graph=QFormLayout();style.addLayout(graph)
        combo(graph,'resource_palette','图表配色',[('跟随整体','theme'),('活力原色','vivid'),('自定义','custom')],cfg['resource_palette'],self.fields)
        colors=QHBoxLayout();style.addLayout(colors);self.swatches={}
        for key,title in [('cpu','CPU'),('memory','内存'),('network','网速'),('gpu','GPU')]:
            b=QPushButton(title);b.clicked.connect(lambda checked=False,key=key:self.choose(key));colors.addWidget(b);self.swatches[key]=b
        self.color_preview();style.addStretch()

        footer=QHBoxLayout();self.status=QLabel();self.status.setWordWrap(True);footer.addWidget(self.status,1)
        footer.addWidget(button('关闭',self.reject));footer.addWidget(button('保存设置',self.commit,'primary'));box.addLayout(footer)
        from ui_style import compact_dialog
        from settings_layout import fit_auxiliary_dialog
        compact_dialog(self);fit_auxiliary_dialog(self,cfg)

    def install_driver(self):
        from pawnio_setup import launch
        try:launch();self.status.setText('已打开内置安装程序。')
        except (OSError,ValueError) as error:self.status.setText(str(error))

    def pick_background(self):
        color=QColorDialog.getColor(QColor(self.color.text() or '#8fbfe0'),self,'背景主题色')
        if color.isValid():self.color.setText(color.name())

    def color_preview(self):
        for key,b in self.swatches.items():b.setStyleSheet('border-bottom:3px solid '+self.tints.get(key,TINTS[key])+';')
    def choose(self,key):
        color=QColorDialog.getColor(QColor(self.tints.get(key,TINTS[key])),self,'图表颜色')
        if color.isValid():
            self.tints[key]=color.name();self.fields['resource_palette'].setCurrentIndex(self.fields['resource_palette'].findData('custom'));self.color_preview()

    def commit(self):
        def value(widget):
            if isinstance(widget,ModernComboBox):return widget.currentData()
            if isinstance(widget,ModernSpinBox):return widget.value()
            return widget.isChecked()
        changes={key:value(widget) for key,widget in self.fields.items()}
        changes['resource_task_metrics']=[key for key,widget in self.task_fields.items() if widget.isChecked()]
        changes['resource_tints']=dict(self.tints)
        custom={key:value(widget) for key,widget in self.custom_fields.items()}
        custom['color']=self.color.text().strip().lower()
        if changes['resource_background']=='custom' or self.service.cfg['resource_appearance'] or custom!=(self.baseline['resource_appearance'] or background(self.baseline)):
            try:changes['resource_appearance']=clean_background(custom,True)
            except ValueError:
                self.status.setText('请输入 #RRGGBB 颜色值，或点击「默认」。');return False
        changes={k:v for k,v in changes.items() if v!=self.baseline.get(k)}
        ok=self.service.set_options(**changes) if changes else True
        if ok:self.baseline.update(changes)
        self.status.setText('已保存。' if ok else '保存失败，请重试。')
        return ok
