"""Preferences shared by the desktop monitor and the independent taskbar readout."""
from weakref import proxy
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QWidget,QDialog,QTabWidget,QFrame,QLabel,QPushButton,QLineEdit,QColorDialog,QScrollArea,
                             QVBoxLayout,QHBoxLayout,QGridLayout,QFormLayout,QListWidget,QListWidgetItem,QAbstractItemView)
from appearance_presets import COLOR_MODES,material_choices
from resource_options import METRICS,TINTS,TASK_METRICS,COMPACT_METRICS,PINNABLE,AI_PROVIDERS,SENSOR_UNITS,TASK_MEDIA_PARTS,TASK_COLUMN_NAMES,OPEN_PAGES,background,clean_background
from ui_style import SettingsHeader,ModernComboBox,ModernSpinBox,ModernCheckBox,ColorSwatch,THEME_COLORS,button


class OptionFields(dict):
    def __init__(self,owner):super().__init__();self.owner=proxy(owner)
    def __missing__(self,key):
        for index,keys in enumerate(self.owner.field_pages):
            if key in keys:self.owner.ensure_page(index);break
        if dict.__contains__(self,key):return dict.__getitem__(self,key)
        raise KeyError(key)


class PageFields(dict):
    def __init__(self,owner,page):super().__init__();self.owner=proxy(owner);self.page=page
    def __getitem__(self,key):self.owner.ensure_page(self.page);return super().__getitem__(key)
    def items(self):self.owner.ensure_page(self.page);return super().items()
    def __iter__(self):self.owner.ensure_page(self.page);return super().__iter__()


class ResourceOptions(QDialog):
    page_stores = {
        1: ('task_fields', 'task_media_fields'),
        2: ('compact_fields', 'pinned_fields'),
        3: ('ai_fields',),
        4: ('custom_fields',),
        5: ('limit_fields',),
    }
    field_pages=[
        {'resource_'+key for key in METRICS}|{'resource_enabled','resource_auto_hide','resource_bt_tray','resource_hide_unavailable','resource_layer','resource_fold','resource_interval','resource_delay','resource_open_page'},
        {'resource_taskbar','resource_task_threshold','resource_task_music','resource_task_music_colorful','resource_taskbar_position','resource_taskbar_layer','resource_task_font'},
        {'resource_compact_auto_width','resource_compact_width','resource_compact_height','resource_expanded_width','resource_expanded_height','resource_compact_density','resource_compact_rings','resource_clock','resource_compact_rotate','resource_ring_letters','resource_quota_alert'},
        {'resource_ai','resource_ai_tray','resource_music','resource_lyrics','resource_music_text','resource_equalizer'},
        {'resource_halo','resource_halo_speed','resource_threshold','resource_background','resource_palette'},set(),
        {'resource_edge_snap','resource_liquid','resource_face','resource_face_interactive','resource_live_glass','resource_expand_mode','resource_face_mood','resource_face_scale'},
        {'resource_weather','resource_weather_compact','resource_weather_days'}]

    def ensure_page(self,index):
        if index in self.loaded:return
        self.loaded.add(index);self.builders[index]()
        draft = self.drafts.get(index)
        if draft:
            for name, values in draft['stores'].items():
                store = getattr(self, name)
                for key, value in values.items():
                    widget = store[key]
                    blocked = widget.blockSignals(True)
                    if isinstance(widget, ModernComboBox):
                        widget.setCurrentIndex(max(0, widget.findData(value)))
                    elif isinstance(widget, ModernSpinBox):
                        widget.setValue(value)
                        widget.sync_steps()
                    else:
                        widget.setChecked(value)
                    widget.blockSignals(blocked)
            if index == 4:
                self.color.setText(draft['text'])
            elif index == 7:
                self.weather_cities.setText(draft['text'])
        root = self.tabs.widget(index)
        for form in root.findChildren(QFormLayout):
            form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        if self.property('densityApplied'):
            from settings_layout import apply_density, capture_density
            from ui_style import compact_widget_tree
            compact_widget_tree(root)
            apply_density(capture_density(root), float(self.property('interfaceScale') or .7))
        if draft:
            self.tabs.widget(index).findChild(QScrollArea).verticalScrollBar().setValue(draft['scroll'])

    @staticmethod
    def value(widget):
        if isinstance(widget, ModernComboBox):
            return widget.currentData()
        if isinstance(widget, ModernSpinBox):
            return widget.value()
        return widget.isChecked()

    def snapshot_page(self, index):
        stores = {'fields': {key: self.value(self.fields[key]) for key in self.field_pages[index] if key in self.fields}}
        for name in self.page_stores.get(index, ()):
            stores[name] = {key: self.value(widget) for key, widget in dict.items(getattr(self, name))}
        text = self.color.text() if index == 4 else self.weather_cities.text() if index == 7 else ''
        scroll = self.tabs.widget(index).findChild(QScrollArea).verticalScrollBar().value()
        self.drafts[index] = dict(stores=stores, text=text, scroll=scroll)

    def show_page(self, index):
        for previous in tuple(self.loaded):
            if previous == index:
                continue
            self.snapshot_page(previous)
            for key in self.field_pages[previous]:
                self.fields.pop(key, None)
            for name in self.page_stores.get(previous, ()):
                getattr(self, name).clear()
            if previous == 4:
                self.color = None
                self.swatches = {}
            elif previous == 7:
                self.weather_cities = None
            self.loaded.remove(previous)
            scroll = self.tabs.widget(previous).layout().takeAt(0).widget()
            scroll.hide()
            scroll.deleteLater()
        if index >= 0:
            self.ensure_page(index)

    def __init__(self,service):
        budget=getattr(service.runtime,'memory_budget',None)
        if budget:budget.prepare_settings()
        super().__init__(None,Qt.Window|Qt.FramelessWindowHint|Qt.WindowMinimizeButtonHint)
        self.setProperty('simpleForms', True)
        self.service=service;cfg=service.cfg
        self.setWindowTitle('资源胶囊设置 · 大肥鱼Dock');self.resize(490,430)
        self.loaded=set();self.fields=OptionFields(self);self.tints=dict(cfg['resource_tints'])
        self.drafts = {}
        self.orders = {}
        for name,index in [('custom_fields',4),('task_fields',1),('task_media_fields',1),('compact_fields',2),('pinned_fields',2),('ai_fields',3),('limit_fields',5)]:
            setattr(self,name,PageFields(self,index))
        from copy import deepcopy
        self.baseline = {key: deepcopy(value) if key.startswith('resource_') else value for key, value in cfg.items()
                         if key.startswith(('resource_', 'panel_'))}
        box=QVBoxLayout(self);box.addWidget(SettingsHeader(self,'资源胶囊设置'))
        self.tabs=QTabWidget();box.addWidget(self.tabs,1)
        pages={}
        for name in ('桌面监控','任务栏监控','收起显示','AI 与音乐','背景与配色','阈值上限','液态与表情','天气'):
            pages[name]=QWidget();self.tabs.addTab(pages[name],name)
        def page(name):
            scroll=QScrollArea();scroll.setFrameShape(QFrame.NoFrame);scroll.setWidgetResizable(True)
            part=QWidget();layout=QVBoxLayout(part);scroll.setWidget(part)
            outer = pages[name].layout()
            if outer is None:
                outer = QVBoxLayout(pages[name])
                outer.setContentsMargins(0, 0, 0, 0)
            outer.addWidget(scroll)
            return layout
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

        def build_0():
            desktop=page('桌面监控')
            for key,title in [('resource_enabled','显示资源胶囊'),('resource_auto_hide','鼠标离开后收起'),('resource_bt_tray','蓝牙电量托盘图标'),('resource_hide_unavailable','隐藏未提供读数的传感器')]:
                self.fields[key]=check(title,cfg[key]);desktop.addWidget(self.fields[key])
            form=QFormLayout();desktop.addLayout(form)
            combo(form,'resource_open_page','展开首选页面',[(label,key) for key,label in OPEN_PAGES.items()],cfg['resource_open_page'],self.fields)
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

        def build_1():
            bar=page('任务栏监控')
            self.fields['resource_taskbar']=check('显示任务栏监控',cfg['resource_taskbar']);bar.addWidget(self.fields['resource_taskbar'])
            placement_form=QFormLayout();bar.addLayout(placement_form)
            combo(placement_form,'resource_taskbar_position','任务栏位置',[('靠左','left'),('居中','center'),('靠右','right')],cfg['resource_taskbar_position'],self.fields)
            from resource_options import TASKBAR_LAYERS
            combo(placement_form,'resource_taskbar_layer','显示层级',[(title,key) for key,title in TASKBAR_LAYERS.items()],cfg['resource_taskbar_layer'],self.fields)
            self.fields['resource_task_threshold']=check('文字阈值变色（关闭时跟随系统字体颜色）',cfg['resource_task_threshold']);bar.addWidget(self.fields['resource_task_threshold'])
            self.fields['resource_task_music']=check('横向任务栏显示音乐（封面、控制与律动）',cfg['resource_task_music']);bar.addWidget(self.fields['resource_task_music'])
            self.fields['resource_task_music_colorful']=check('音乐多彩样式（频谱与进度线）',cfg['resource_task_music_colorful']);bar.addWidget(self.fields['resource_task_music_colorful'])
            media_grid=QGridLayout();bar.addLayout(media_grid)
            for i,(key,title) in enumerate(TASK_MEDIA_PARTS.items()):
                field=check(title,key in cfg['resource_task_media_parts']);self.task_media_fields[key]=field;media_grid.addWidget(field,i//3,i%3)
            note=QLabel('可只保留频谱或封面图标；关闭的组件让出空间，全部取消则只显示资源读数。');note.setWordWrap(True);bar.addWidget(note)
            font_form=QFormLayout();bar.addLayout(font_form)
            hint=QLabel('固定显示，不通过拖动定位；自动避让开始菜单、应用按钮和系统托盘。');hint.setWordWrap(True);bar.addWidget(hint)
            spin(font_form,'resource_task_font','字体大小（像素）',2,24,cfg['resource_task_font'],self.fields)
            note=QLabel('缩小字号时，文字、间距和音乐组件同步收紧；空间不足时改为单行或分页。');note.setWordWrap(True);bar.addWidget(note)
            controls=QGridLayout();bar.addLayout(controls)
            for i,key in enumerate(TASK_METRICS):
                field=check(METRICS[key],key in cfg['resource_task_metrics']);self.task_fields[key]=field;controls.addWidget(field,i//3,i%3)
            bar.addWidget(button('监控列排序…', lambda: self.edit_order('resource_task_order', TASK_COLUMN_NAMES)))
            bar.addStretch()

        def build_2():
            compact=page('收起显示');compact_form=QFormLayout();compact.addLayout(compact_form)
            self.fields['resource_compact_auto_width']=check('宽度随内容收紧（不超过设定宽度）',cfg['resource_compact_auto_width']);compact.addWidget(self.fields['resource_compact_auto_width'])
            spin(compact_form,'resource_compact_width','胶囊宽度',96,1400,cfg['resource_compact_width'],self.fields)
            spin(compact_form,'resource_compact_height','胶囊高度',28,100,cfg['resource_compact_height'],self.fields)
            spin(compact_form,'resource_expanded_width','展开宽度（各页共用）',260,1000,cfg['resource_expanded_width'],self.fields)
            spin(compact_form,'resource_expanded_height','展开高度（各页共用）',180,800,cfg['resource_expanded_height'],self.fields)
            combo(compact_form,'resource_compact_density','内容密度',[('自动紧凑','auto'),('始终紧凑','dense')],cfg['resource_compact_density'],self.fields)
            for key,title in [('resource_compact_rings','资源占用环'),('resource_clock','显示时间'),('resource_compact_rotate','读数自动翻页'),
                              ('resource_ring_letters','配额环内显示首字母'),('resource_quota_alert','额度剩余降至 40% / 20% 时提醒 5 秒')]:
                self.fields[key]=check(title,cfg[key]);compact.addWidget(self.fields[key])
            compact.addWidget(QLabel('收起时保留的读数（须先启用对应监控项）'))
            compact_grid=QGridLayout();compact.addLayout(compact_grid)
            for i,key in enumerate(COMPACT_METRICS):
                field=check(METRICS[key],key in cfg['resource_compact_metrics']);self.compact_fields[key]=field;compact_grid.addWidget(field,i//3,i%3)
            compact.addWidget(QLabel('优先常驻项（须启用对应组件；传感器须勾选保留）'))
            hint=QLabel('开启表情后固定预留左侧位置；常驻项优先保留，其余内容轮播。时间、蓝牙环按剩余空间显示。');hint.setWordWrap(True);compact.addWidget(hint)
            pinned_grid=QGridLayout();compact.addLayout(pinned_grid)
            for i,(key,title) in enumerate(PINNABLE.items()):
                field=check(title,key in cfg['resource_compact_pinned']);self.pinned_fields[key]=field;pinned_grid.addWidget(field,i//3,i%3)
            compact.addWidget(button('读数排序…', lambda: self.edit_order('resource_compact_order', PINNABLE)))
            compact.addStretch()

        def build_3():
            deck=page('AI 与音乐')
            for key,title in [('resource_ai','桌面 AI 额度与用量'),('resource_ai_tray','独立 AI 用量托盘图标'),('resource_music','音乐预览与控制'),('resource_lyrics','同步歌词（允许联网匹配）')]:
                self.fields[key]=check(title,cfg[key]);deck.addWidget(self.fields[key])
            provider_grid=QGridLayout();deck.addLayout(provider_grid)
            for i,key in enumerate(AI_PROVIDERS):
                field=check(key,key in cfg['resource_ai_providers']);self.ai_fields[key]=field;provider_grid.addWidget(field,i//3,i%3)
            info=QLabel('最多选择 7 个工具。读取本机已登录账号和用量记录；未连接时显示实际状态。');info.setWordWrap(True);deck.addWidget(info)
            from deck_runtime import installed_runtime,RUNTIME_URL
            runtime_note=QLabel('已检测到 .NET 10 桌面运行库' if installed_runtime() else 'AI / 音乐需要安装 .NET 10 桌面运行库（x64）');runtime_note.setWordWrap(True);deck.addWidget(runtime_note)
            from PyQt5.QtGui import QDesktopServices
            from PyQt5.QtCore import QUrl
            deck.addWidget(button('打开运行库下载页',lambda:QDesktopServices.openUrl(QUrl(RUNTIME_URL))))
            music_form=QFormLayout();deck.addLayout(music_form)
            combo(music_form,'resource_music_text','收起时显示',[('声音律动','wave'),('歌名','title'),('当前歌词','lyrics')],cfg['resource_music_text'],self.fields)
            combo(music_form,'resource_equalizer','音乐律动',[('声音流动','flow'),('频谱','spectrum')],cfg['resource_equalizer'],self.fields)
            deck.addStretch()

        def build_4():
            style=page('背景与配色');style_form=QFormLayout();style.addLayout(style_form)
            from resource_options import HALO_SPEEDS
            combo(style_form,'resource_halo_speed','光环流动速度',[(title,key) for key,(title,_) in HALO_SPEEDS.items()],cfg['resource_halo_speed'],self.fields)
            for key,title in [('resource_halo','彩色流动光环'),('resource_threshold','胶囊阈值变色：低于 60% 绿，60–80% 黄，80% 起红')]:
                self.fields[key]=check(title,cfg[key]);style.addWidget(self.fields[key])
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

        def build_5():
            thresholds=page('阈值上限');tip=QLabel('按上限的 60% 变黄、80% 变红。占用率上限为 100%；温度默认 100°C。其他指标设置上限后参与变色，0 表示不变色。');tip.setWordWrap(True);thresholds.addWidget(tip)
            limits_form=QFormLayout();thresholds.addLayout(limits_form)
            from resource_status import default_limit
            for key,unit in SENSOR_UNITS.items():
                if key=='gpu_memory':continue
                spin(limits_form,key,METRICS[key]+'（'+unit+'）',0,100000,cfg['resource_limits'].get(key,default_limit(key)),self.limit_fields)
            thresholds.addStretch()

        def build_6():
            interaction=page('液态与表情')
            for key,title in [('resource_edge_snap','资源胶囊参与卡片吸附'),('resource_liquid','液态拉伸、断开水滴与贴边圆角'),
                              ('resource_face','显示表情（收起与展开）'),('resource_face_interactive','表情互动（跟随、眨眼与按压）'),('resource_live_glass','实时毛玻璃背景')]:
                self.fields[key]=check(title,cfg[key]);interaction.addWidget(self.fields[key])
            face_form=QFormLayout();interaction.addLayout(face_form)
            combo(face_form,'resource_expand_mode','展开方式',[('鼠标移入展开','hover'),('仅点击展开','click')],cfg['resource_expand_mode'],self.fields)
            combo(face_form,'resource_face_mood','表情样式',list(zip(('靠近随机变化','默认','开心','眨眼','爱心','星星眼','害羞','嘟嘴','眯眼'),('random','default','happy','wink','love','star','shy','pout','squint'))),cfg['resource_face_mood'],self.fields)
            spin(face_form,'resource_face_scale','表情大小（%）',60,130,cfg['resource_face_scale'],self.fields)
            hint=QLabel('吸附距离在主设置的「桌面收纳」调整。精简模式保留表情跟随，暂停实时背景采集。')
            hint.setWordWrap(True);interaction.addWidget(hint);interaction.addStretch()

        def build_7():
            daily=page('天气')
            for key,title in [('resource_weather','显示天气'),('resource_weather_compact','天气加入收起读数')]:
                self.fields[key]=check(title,cfg[key]);daily.addWidget(self.fields[key])
            daily.addWidget(QLabel('天气城市（最多 6 个，以逗号分隔）'))
            self.weather_cities=QLineEdit('，'.join(cfg['resource_weather_cities']));self.weather_cities.setAccessibleName('天气城市');daily.addWidget(self.weather_cities)
            weather_form=QFormLayout();daily.addLayout(weather_form)
            combo(weather_form,'resource_weather_days','天气范围',[('昨天、今天、明天',3),('未来一周（今天起 7 天）',7),('仅今天',1),('今天、明天',2),('今天起 4 天',4),('今天起 5 天',5),('今天起 6 天',6)],cfg['resource_weather_days'],self.fields)
            hint=QLabel('默认天津、乌鲁木齐、沈阳。天气联网获取。')
            hint.setWordWrap(True);daily.addWidget(hint);daily.addStretch()

        self.builders=[build_0,build_1,build_2,build_3,build_4,build_5,build_6,build_7]
        self.tabs.currentChanged.connect(self.show_page)
        self.ensure_page(0)

        footer=QHBoxLayout();self.status=QLabel();self.status.setWordWrap(True);footer.addWidget(self.status,1)
        footer.addWidget(button('关闭',self.reject));footer.addWidget(button('保存设置',self.commit,'primary'));box.addLayout(footer)
        from ui_style import compact_dialog
        from settings_layout import fit_auxiliary_dialog
        compact_dialog(self);fit_auxiliary_dialog(self,cfg)

    def install_driver(self):
        from pawnio_setup import launch
        try:launch();self.status.setText('已打开内置安装程序。')
        except (OSError,ValueError) as error:self.status.setText(str(error))

    def deleteLater(self):
        # Page builders close over the dialog and its placeholder widgets.
        # Break that Python cycle while the Qt parent tree is still alive.
        self.builders.clear()
        self.fields.clear()
        for names in self.page_stores.values():
            for name in names:
                getattr(self, name).clear()
        super().deleteLater()

    def pick_background(self):
        color=QColorDialog.getColor(QColor(self.color.text() or '#8fbfe0'),self,'背景主题色')
        if color.isValid():self.color.setText(color.name())

    def color_preview(self):
        for key,b in self.swatches.items():b.setStyleSheet('border-bottom:3px solid '+self.tints.get(key,TINTS[key])+';')
    def choose(self,key):
        color=QColorDialog.getColor(QColor(self.tints.get(key,TINTS[key])),self,'图表颜色')
        if color.isValid():
            self.tints[key]=color.name();self.fields['resource_palette'].setCurrentIndex(self.fields['resource_palette'].findData('custom'));self.color_preview()

    def edit_order(self, key, names):
        order = self.orders.get(key, self.service.cfg[key])
        if key == 'resource_compact_order' and not order:
            order = self.service.cfg['resource_compact_pinned']
        order = [item for item in dict.fromkeys([*order, *names]) if item in names]
        dialog = QDialog(self)
        dialog.setWindowTitle('显示顺序')
        dialog.resize(380, 390)
        layout = QVBoxLayout(dialog)
        hint = QLabel('拖动项目调整顺序，也可使用上移和下移。')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        view = QListWidget()
        view.setDragDropMode(QAbstractItemView.InternalMove)
        view.setDefaultDropAction(Qt.MoveAction)
        for item in order:
            row = QListWidgetItem(names[item])
            row.setData(Qt.UserRole, item)
            view.addItem(row)
        view.setCurrentRow(0)
        layout.addWidget(view, 1)

        def move(delta):
            row = view.currentRow()
            if row >= 0 and 0 <= row + delta < view.count():
                item = view.takeItem(row)
                view.insertItem(row + delta, item)
                view.setCurrentItem(item)

        controls = QHBoxLayout()
        controls.addWidget(button('上移', lambda: move(-1)))
        controls.addWidget(button('下移', lambda: move(1)))
        controls.addStretch()
        controls.addWidget(button('取消', dialog.reject))
        controls.addWidget(button('确定', dialog.accept, 'primary'))
        layout.addLayout(controls)
        try:
            if dialog.exec_() == QDialog.Accepted:
                self.orders[key] = [view.item(i).data(Qt.UserRole) for i in range(view.count())]
        finally:
            dialog.deleteLater()

    def commit(self):
        for index in self.loaded:
            self.snapshot_page(index)
        changes = dict(self.orders)
        for draft in self.drafts.values():
            changes.update(draft['stores']['fields'])
        if 7 in self.drafts:
            import re
            from resource_weather import clean_cities
            try:changes['resource_weather_cities']=clean_cities([s.strip() for s in re.split('[,，;；]',self.drafts[7]['text']) if s.strip()],True)
            except ValueError as error:self.status.setText(str(error));return False
        for index,key,name in [(1,'resource_task_metrics','task_fields'),(1,'resource_task_media_parts','task_media_fields'),
                               (2,'resource_compact_metrics','compact_fields'),(2,'resource_compact_pinned','pinned_fields'),
                               (3,'resource_ai_providers','ai_fields')]:
            if index in self.drafts:
                selected = self.drafts[index]['stores'][name]
                # Preserve the saved priority of checked items across tab changes.
                order = dict.fromkeys([*self.baseline[key], *selected])
                changes[key] = [item for item in order if selected.get(item)]
        if 5 in self.drafts:
            from resource_status import default_limit
            changes['resource_limits']={k:value for k,value in self.drafts[5]['stores']['limit_fields'].items() if value!=default_limit(k)}
        if len(changes.get('resource_ai_providers',[]))>7:self.status.setText('最多同时显示 7 个 AI 工具。');return False
        if 4 in self.drafts:
            changes['resource_tints']=dict(self.tints)
            custom=dict(self.drafts[4]['stores']['custom_fields'], color=self.drafts[4]['text'].strip().lower())
            if changes['resource_background']=='custom' or self.service.cfg['resource_appearance'] or custom!=(self.baseline['resource_appearance'] or background(self.baseline)):
                try:changes['resource_appearance']=clean_background(custom,True)
                except ValueError:
                    self.status.setText('请输入 #RRGGBB 颜色值，或点击「默认」。');return False
        changes={k:v for k,v in changes.items() if v!=self.baseline.get(k)}
        ok=self.service.set_options(**changes) if changes else True
        if ok:self.baseline.update(changes)
        self.status.setText('已保存。' if ok else '保存失败，请重试。')
        return ok
