"""Preferences shared by the desktop monitor and the independent taskbar readout."""
from weakref import proxy
from PyQt5.QtCore import QSize,Qt
from PyQt5.QtGui import QColor,QFont,QPalette
from PyQt5.QtWidgets import (QWidget,QDialog,QStackedWidget,QFrame,QLabel,QPushButton,QLineEdit,QColorDialog,QScrollArea,
                             QVBoxLayout,QHBoxLayout,QGridLayout,QFormLayout,QListWidget,QListWidgetItem,
                             QAbstractItemView,QStyledItemDelegate)
from appearance_presets import COLOR_MODES,material_choices
from resource_options import METRICS,TINTS,TASK_METRICS,PINNABLE,AI_PROVIDERS,SENSOR_UNITS,TASK_MEDIA_PARTS,TASK_COLUMN_NAMES,OPEN_PAGES,background,clean_background
from resource_options import (CAPSULE_PAGES,CAPSULE_TASKBAR_POSITIONS,COMPACT_BADGE_HEIGHT_RANGE,COMPACT_CLOCK_FORMATS,COMPACT_CONTENT,COMPACT_ITEMS,COMPACT_ROUTINES,COMPACT_STATUS,
                              DESKTOP_COMPONENTS,FACE_SWITCH_RANGE,PLACED_COMPONENTS,REMINDER_OPTIONS,clean_weather_thresholds,component_location)
from settings_design import NumericControl,SettingsNavigation
from ui_style import SettingsHeader,ModernComboBox,ModernSpinBox,ModernCheckBox,ColorSwatch,THEME_COLORS,button


PAGE_NAMES = ('胶囊行为','任务栏监控','收起显示','AI 与音乐','材质与配色','资源与阈值','表情与吸附','天气与订阅','组件布局','日程与提醒')
NAV_SYMBOLS = ('startup','position','size','wave','palette','monitor','corner','notes','panels','calendar')
NAV_GROUPS = (('胶囊',(0,2,4,6,8)),('监控',(5,1)),('内容与接入',(9,7,3)))
COMPACT_GROUPS = (
    ('性能与流量', ('cpu','gpu','memory','network','fps','traffic')),
    ('电脑状态（右侧图标）', COMPACT_STATUS),
    ('专注与日程', tuple(COMPACT_ROUTINES)),
    ('内容', tuple(COMPACT_CONTENT)),
    ('CPU 传感器', ('cpu_temp','cpu_power','cpu_frequency','cpu_voltage','cpu_fan','cpu_pump')),
    ('GPU 传感器', ('gpu_temp','gpu_power','gpu_frequency','gpu_fan','gpu_memory')),
    ('主板与机箱', ('disk_temp','board_temp','case_temp','board_fan')),
)
PLACEMENT_GROUPS = (
    ('监控与媒体', ('resources','ai','music','traffic')),
    ('日常内容', ('weather','pomodoro','agenda','news')),
    ('桌面组件', tuple(DESKTOP_COMPONENTS)),
)


class ResourceNavDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        if index.data(Qt.UserRole) is not None:
            return super().paint(painter, option, index)
        rect = option.rect.adjusted(7, 3 if index.row() else 0, -5, 0)
        ink = option.palette.color(QPalette.Disabled,QPalette.WindowText)
        painter.save()
        painter.setPen(ink)
        painter.setFont(index.data(Qt.FontRole) or option.font)
        painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, index.data(Qt.DisplayRole))
        painter.restore()


def section(parent, title):
    box = QWidget()
    box.setObjectName('SettingsGroup')
    box.setAttribute(Qt.WA_StyledBackground)
    layout = QVBoxLayout(box)
    layout.setContentsMargins(12,9,12,10)
    layout.setSpacing(7)
    heading = QLabel(title)
    heading.setProperty('role','group-title')
    layout.addWidget(heading)
    parent.addWidget(box)
    return layout


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
        2: ('compact_fields',),
        3: ('ai_fields',),
        4: ('custom_fields',),
        5: ('limit_fields','weather_threshold_fields'),
        8: ('location_fields',),
    }
    field_pages=[
        {'resource_enabled','resource_auto_hide','resource_layer','resource_fold','resource_delay','resource_open_page','resource_click_through','resource_expand_mode',
         'resource_capsule_taskbar','resource_capsule_taskbar_position'},
        {'resource_taskbar','resource_task_threshold','resource_task_music','resource_task_music_colorful','resource_taskbar_position','resource_taskbar_layer','resource_task_font','resource_taskbar_click_through'},
        {'resource_compact_auto_width','resource_compact_width','resource_compact_height','resource_compact_badge_height','resource_expanded_width','resource_expanded_height','resource_compact_density','resource_compact_rings','resource_clock','resource_clock_format','resource_compact_rotate','resource_weather_compact','resource_compact_ai','resource_compact_music','resource_alert_battery'},
        {'resource_ai','resource_ai_tray','resource_quota_alert','resource_music','resource_lyrics','resource_music_text','resource_equalizer'},
        {'resource_halo','resource_halo_speed','resource_background','resource_palette','resource_card_transparency'},
        {'resource_'+key for key in METRICS}|{'resource_threshold','resource_interval','resource_bt_tray','resource_hide_unavailable'},
        {'resource_edge_snap','resource_peer_snap','resource_liquid','resource_face','resource_face_interactive','resource_face_mood','resource_face_role','resource_face_scale',
         'resource_face_auto_switch','resource_face_switch_minutes'},
        {'resource_weather','resource_weather_days','resource_air_source','resource_news'},set(),
        {'resource_pomodoro','resource_agenda','resource_alert_agenda','resource_alert_focus','resource_alert_water','resource_reminder_sound'}]

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
                    if key == 'resource_face_role':
                        widget.select(value)
                    elif isinstance(widget, ModernComboBox):
                        widget.setCurrentIndex(max(0, widget.findData(value)))
                    elif isinstance(widget, ModernSpinBox):
                        widget.setValue(value)
                        widget.sync_steps()
                        control=widget.parentWidget()
                        if isinstance(control,NumericControl):control.slider.setValue(value)
                    else:
                        widget.setChecked(value)
                    widget.blockSignals(blocked)
            if index == 4:
                self.color.setText(draft['text'])
            elif index == 2:
                self.fields['resource_clock_format'].setEnabled(self.fields['resource_clock'].isChecked())
            elif index == 6:
                self.fields['resource_face_switch_minutes'].setEnabled(self.fields['resource_face_auto_switch'].isChecked())
            elif index == 7:
                self.weather_cities.setText(draft['text'])
                self.news_feeds.setPlainText(draft['feeds'])
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
        if index == 7:
            self.drafts[index]['feeds'] = self.news_feeds.toPlainText()

    def show_page(self, index):
        if index >= 0 and self.nav.currentItem() is not self.nav_items[index]:
            self.nav.setCurrentItem(self.nav_items[index])
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
                self.news_feeds = None
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
        self.setWindowTitle('资源胶囊设置 · 大肥鱼Dock');self.resize(598,506)
        self.loaded=set();self.fields=OptionFields(self);self.tints=dict(cfg['resource_tints'])
        self.drafts = {}
        self.orders = {}
        for name,index in [('custom_fields',4),('task_fields',1),('task_media_fields',1),('compact_fields',2),('ai_fields',3),('limit_fields',5),('weather_threshold_fields',5),('location_fields',8)]:
            setattr(self,name,PageFields(self,index))
        from copy import deepcopy
        self.baseline = {key: deepcopy(value) if key.startswith('resource_') else value for key, value in cfg.items()
                         if key.startswith(('resource_', 'panel_'))}
        box=QVBoxLayout(self);box.addWidget(SettingsHeader(self,'资源胶囊设置'))
        content = QHBoxLayout()
        content.setSpacing(10)
        box.addLayout(content,1)
        self.nav = SettingsNavigation()
        self.nav.setAccessibleName('资源胶囊设置分类')
        self.nav.setItemDelegate(ResourceNavDelegate(self.nav))
        content.addWidget(self.nav)
        self.tabs = QStackedWidget()
        content.addWidget(self.tabs,1)
        for _ in PAGE_NAMES:
            self.tabs.addWidget(QWidget())
        self.nav_items = {}
        for group, indices in NAV_GROUPS:
            heading = QListWidgetItem(group)
            heading.setFlags(Qt.NoItemFlags)
            self.nav.addItem(heading)
            for index in indices:
                self.nav_items[index] = self.nav.add_page(PAGE_NAMES[index],NAV_SYMBOLS[index],index)

        def page(index):
            scroll=QScrollArea();scroll.setFrameShape(QFrame.NoFrame);scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            part=QWidget();layout=QVBoxLayout(part);scroll.setWidget(part)
            layout.setContentsMargins(1,1,6,1)
            layout.setSpacing(9)
            root = self.tabs.widget(index)
            outer = root.layout()
            if outer is None:
                outer = QVBoxLayout(root)
                outer.setContentsMargins(0, 0, 0, 0)
            outer.addWidget(scroll)
            heading=QLabel(PAGE_NAMES[index])
            heading.setProperty('role','group-title')
            layout.addWidget(heading)
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
            layout=page(0)
            desktop=section(layout,'显示与层级')
            self.fields['resource_enabled']=check('显示资源胶囊',cfg['resource_enabled']);desktop.addWidget(self.fields['resource_enabled'])
            form=QFormLayout();desktop.addLayout(form)
            combo(form,'resource_open_page','展开后默认页面',[(label,key) for key,label in OPEN_PAGES.items()],cfg['resource_open_page'],self.fields)
            combo(form,'resource_layer','桌面层级',[('置顶','top'),('置底','bottom')],cfg['resource_layer'],self.fields)
            combo(form,'resource_fold','收起形态',[('胶囊','pill'),('圆球','ball'),('方条','bar')],cfg['resource_fold'],self.fields)
            taskbar=section(layout,'任务栏固定')
            pinned=check('收起时固定到任务栏',cfg['resource_capsule_taskbar'])
            self.fields['resource_capsule_taskbar']=pinned;taskbar.addWidget(pinned)
            form=QFormLayout();taskbar.addLayout(form)
            position=combo(form,'resource_capsule_taskbar_position','固定位置',[(label,key) for key,label in CAPSULE_TASKBAR_POSITIONS.items()],
                           cfg['resource_capsule_taskbar_position'],self.fields)
            position.setEnabled(pinned.isChecked());pinned.toggled.connect(position.setEnabled)
            hint=QLabel('拖动胶囊可调整固定位置。任务栏空位不足时，胶囊暂留桌面。')
            hint.setObjectName('Subtle');hint.setWordWrap(True);taskbar.addWidget(hint)
            behavior=section(layout,'展开与收起')
            form=QFormLayout();behavior.addLayout(form)
            combo(form,'resource_expand_mode','展开方式',[('鼠标移入展开','hover'),('仅点击展开','click')],cfg['resource_expand_mode'],self.fields)
            spin(form,'resource_delay','收起延迟（秒）',1,30,cfg['resource_delay'],self.fields)
            for key,title in [('resource_auto_hide','鼠标离开后收起'),('resource_click_through','鼠标穿透（可从托盘关闭）')]:
                self.fields[key]=check(title,cfg[key]);behavior.addWidget(self.fields[key])
            layout.addStretch()

        def build_1():
            layout=page(1)
            bar=section(layout,'位置与文字')
            self.fields['resource_taskbar']=check('显示任务栏监控',cfg['resource_taskbar']);bar.addWidget(self.fields['resource_taskbar'])
            placement_form=QFormLayout();bar.addLayout(placement_form)
            combo(placement_form,'resource_taskbar_position','任务栏位置',[('靠左','left'),('居中','center'),('靠右','right')],cfg['resource_taskbar_position'],self.fields)
            from resource_options import TASKBAR_LAYERS
            combo(placement_form,'resource_taskbar_layer','显示层级',[(title,key) for key,title in TASKBAR_LAYERS.items()],cfg['resource_taskbar_layer'],self.fields)
            self.fields['resource_taskbar_click_through']=check('鼠标穿透（可从托盘设置关闭）',cfg['resource_taskbar_click_through']);bar.addWidget(self.fields['resource_taskbar_click_through'])
            self.fields['resource_task_threshold']=check('文字阈值变色（关闭时跟随系统字体颜色）',cfg['resource_task_threshold']);bar.addWidget(self.fields['resource_task_threshold'])
            spin(placement_form,'resource_task_font','字体大小（像素）',2,24,cfg['resource_task_font'],self.fields)
            bar=section(layout,'音乐组件')
            self.fields['resource_task_music']=check('横向任务栏显示音乐（封面、控制与律动）',cfg['resource_task_music']);bar.addWidget(self.fields['resource_task_music'])
            self.fields['resource_task_music_colorful']=check('音乐多彩样式（频谱与进度线）',cfg['resource_task_music_colorful']);bar.addWidget(self.fields['resource_task_music_colorful'])
            media_grid=QGridLayout();bar.addLayout(media_grid)
            for i,(key,title) in enumerate(TASK_MEDIA_PARTS.items()):
                field=check(title,key in cfg['resource_task_media_parts']);self.task_media_fields[key]=field;media_grid.addWidget(field,i//3,i%3)
            note=QLabel('可只保留频谱或封面图标；关闭的组件让出空间，全部取消则只显示资源读数。');note.setWordWrap(True);bar.addWidget(note)
            bar=section(layout,'任务栏读数')
            controls=QGridLayout();bar.addLayout(controls)
            for i,key in enumerate(TASK_METRICS):
                field=check(METRICS[key],key in cfg['resource_task_metrics']);self.task_fields[key]=field;controls.addWidget(field,i//3,i%3)
            bar.addWidget(button('监控列排序…', lambda: self.edit_order('resource_task_order', TASK_COLUMN_NAMES)))
            layout.addStretch()

        def build_2():
            layout=page(2)
            readouts=section(layout,'收起时显示的项目')
            tools=QHBoxLayout()
            hint=QLabel('排在前面的已勾选项目优先常驻。');hint.setWordWrap(True)
            tools.addWidget(hint,1)
            tools.addWidget(button('读数排序…',lambda: self.edit_order('resource_compact_order',PINNABLE)))
            readouts.addLayout(tools)
            for title,keys in COMPACT_GROUPS:
                heading=QLabel(title);heading.setProperty('role','group-title');readouts.addWidget(heading)
                grid=QGridLayout();readouts.addLayout(grid)
                for i,key in enumerate(keys):
                    if key in COMPACT_CONTENT:
                        option=COMPACT_CONTENT[key]
                        field=check(PINNABLE[key],cfg[option]);self.fields[option]=field
                    else:
                        field=check(COMPACT_ITEMS[key],key in cfg['resource_compact_metrics']);self.compact_fields[key]=field
                    grid.addWidget(field,i//3,i%3)
            compact=section(layout,'尺寸与分页')
            compact_form=QFormLayout();compact.addLayout(compact_form)
            self.fields['resource_compact_auto_width']=check('宽度随内容收紧（不超过设定宽度）',cfg['resource_compact_auto_width']);compact.addWidget(self.fields['resource_compact_auto_width'])
            spin(compact_form,'resource_compact_width','胶囊宽度',96,1400,cfg['resource_compact_width'],self.fields)
            spin(compact_form,'resource_compact_height','胶囊高度',28,100,cfg['resource_compact_height'],self.fields)
            spin(compact_form,'resource_compact_badge_height','徽标高度',*COMPACT_BADGE_HEIGHT_RANGE,cfg['resource_compact_badge_height'],self.fields)
            self.fields['resource_compact_badge_height'].setSuffix(' px')
            spin(compact_form,'resource_expanded_width','展开宽度（各页共用）',260,1000,cfg['resource_expanded_width'],self.fields)
            spin(compact_form,'resource_expanded_height','展开高度（各页共用）',180,800,cfg['resource_expanded_height'],self.fields)
            combo(compact_form,'resource_compact_density','内容密度',[('自动紧凑','auto'),('始终紧凑','dense')],cfg['resource_compact_density'],self.fields)
            for key,title in [('resource_compact_rings','资源占用环'),('resource_compact_rotate','读数自动翻页')]:
                self.fields[key]=check(title,cfg[key]);compact.addWidget(self.fields[key])
            clock=section(layout,'日期与时间')
            show_clock=check('显示日期或时间',cfg['resource_clock'])
            self.fields['resource_clock']=show_clock;clock.addWidget(show_clock)
            form=QFormLayout();clock.addLayout(form)
            clock_format=combo(form,'resource_clock_format','显示格式',[(label,key) for key,(label,_) in COMPACT_CLOCK_FORMATS.items()],
                               cfg['resource_clock_format'],self.fields)
            clock_format.setEnabled(show_clock.isChecked());show_clock.toggled.connect(clock_format.setEnabled)
            compact=section(layout,'收起时自动提醒')
            key='resource_alert_battery'
            self.fields[key]=check(REMINDER_OPTIONS[key],cfg[key]);compact.addWidget(self.fields[key])
            layout.addStretch()

        def build_3():
            layout=page(3)
            deck=section(layout,'AI 用量')
            deck.addWidget(button('自定义用量接口…',self.gateway_connections))
            for key,title in [('resource_ai','桌面 AI 额度与用量'),('resource_ai_tray','独立 AI 用量托盘图标'),
                              ('resource_quota_alert','额度剩余降至 40% / 20% 时提醒')]:
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
            music=section(layout,'音乐与歌词')
            for key,title in [('resource_music','音乐预览与控制'),('resource_lyrics','同步歌词（允许联网匹配）')]:
                self.fields[key]=check(title,cfg[key]);music.addWidget(self.fields[key])
            music_form=QFormLayout();music.addLayout(music_form)
            combo(music_form,'resource_music_text','收起时显示',[('声音律动','wave'),('歌名','title'),('当前歌词','lyrics')],cfg['resource_music_text'],self.fields)
            combo(music_form,'resource_equalizer','音乐律动',[('声音流动','flow'),('频谱','spectrum')],cfg['resource_equalizer'],self.fields)
            layout.addStretch()

        def build_4():
            layout=page(4)
            style=section(layout,'背景材质')
            style_form=QFormLayout();style.addLayout(style_form)
            source=combo(style_form,'resource_background','背景',[('跟随整体','global'),('单独设置','custom')],cfg['resource_background'],self.fields)
            transparency=ModernSpinBox();transparency.setRange(0,100);transparency.setSuffix('%')
            transparency.setValue(cfg['resource_card_transparency']);transparency.setAccessibleName('卡底透底')
            control=NumericControl(transparency)
            control.setToolTip('默认 20%。数值越高，透出的胶囊底色越多。')
            style_form.addRow('卡底透底',control);self.fields['resource_card_transparency']=transparency
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
            style=section(layout,'图表颜色与光环')
            graph=QFormLayout();style.addLayout(graph)
            combo(graph,'resource_palette','图表配色',[('跟随整体','theme'),('活力原色','vivid'),('自定义','custom')],cfg['resource_palette'],self.fields)
            colors=QHBoxLayout();style.addLayout(colors);self.swatches={}
            for key,title in [('cpu','CPU'),('memory','内存'),('network','网速'),('gpu','GPU')]:
                b=QPushButton(title);b.clicked.connect(lambda checked=False,key=key:self.choose(key));colors.addWidget(b);self.swatches[key]=b
            self.color_preview()
            from resource_options import HALO_SPEEDS
            self.fields['resource_halo']=check('彩色流动光环',cfg['resource_halo'])
            style.addWidget(self.fields['resource_halo'])
            halo=QFormLayout();style.addLayout(halo)
            combo(halo,'resource_halo_speed','光环流动速度',[(title,key) for key,(title,_) in HALO_SPEEDS.items()],cfg['resource_halo_speed'],self.fields)
            layout.addStretch()

        def build_5():
            layout=page(5)
            peripherals=section(layout,'外设电量')
            profiles=self.orders.get('resource_peripheral_profiles',cfg['resource_peripheral_profiles'])
            device_row=QHBoxLayout()
            count=QLabel(f'已添加 {len(profiles)} 台设备' if profiles else '尚未添加 2.4G 外设')
            count.setWordWrap(True)
            device_row.addWidget(count,1)
            device_row.addWidget(button('管理 2.4G 设备…',lambda:self.edit_peripherals(count)))
            peripherals.addLayout(device_row)
            readouts=section(layout,'资源读数')
            form=QFormLayout();readouts.addLayout(form)
            combo(form,'resource_interval','采样间隔',[(str(s)+' 秒',s) for s in (1,2,5)],cfg['resource_interval'],self.fields)
            for key,title in [('resource_bt_tray','蓝牙电量托盘图标'),('resource_hide_unavailable','隐藏未提供读数的传感器')]:
                self.fields[key]=check(title,cfg[key]);readouts.addWidget(self.fields[key])
            grid=QGridLayout();readouts.addLayout(grid)
            for i,(key,title) in enumerate(METRICS.items()):
                field=check(title,cfg['resource_'+key]);self.fields['resource_'+key]=field;grid.addWidget(field,i//3,i%3)
            fan_hint=QLabel('CPU、GPU 和主板风扇仅在读到实际转速时显示。')
            fan_hint.setWordWrap(True);readouts.addWidget(fan_hint)
            from pawnio_setup import installed
            version=installed();driver=QHBoxLayout();readouts.addLayout(driver)
            driver.addWidget(QLabel('PawnIO '+version if version else 'PawnIO 未安装'),1)
            driver.addWidget(button('安装驱动…',self.install_driver))
            thresholds=section(layout,'阈值与颜色')
            self.fields['resource_threshold']=check('按阈值改变读数颜色',cfg['resource_threshold'])
            thresholds.addWidget(self.fields['resource_threshold'])
            tip=QLabel('达到上限的 60% 变黄，80% 变红。占用率上限为 100%，温度默认 100°C。其他读数的上限设为 0 时保持原色。')
            tip.setWordWrap(True);thresholds.addWidget(tip)
            limits_form=QFormLayout();thresholds.addLayout(limits_form)
            from resource_status import default_limit
            for key,unit in SENSOR_UNITS.items():
                if key=='gpu_memory':continue
                spin(limits_form,key,METRICS[key]+'（'+unit+'）',0,100000,cfg['resource_limits'].get(key,default_limit(key)),self.limit_fields)
            weather=section(layout,'收起天气温度颜色')
            form=QFormLayout();weather.addLayout(form)
            labels=('深蓝低于（℃）','绿色从（℃）开始','黄色高于（℃）','红色高于（℃）')
            for index,(label,value) in enumerate(zip(labels,cfg['resource_weather_thresholds'])):
                spin(form,index,label,-80,80,value,self.weather_threshold_fields)
            hint=QLabel('深蓝和绿色之间使用浅蓝。分界值按从低到高排列。')
            hint.setWordWrap(True);weather.addWidget(hint)
            layout.addStretch()

        def build_6():
            layout=page(6)
            interaction=section(layout,'吸附与拖动')
            for key,title in [('resource_edge_snap','屏幕边缘吸附'),('resource_peer_snap','相邻卡片吸附'),
                              ('resource_liquid','液态拉伸、断开水滴与贴边圆角')]:
                self.fields[key]=check(title,cfg[key]);interaction.addWidget(self.fields[key])
            hint=QLabel('吸附距离在主设置「桌面收纳」中调整。')
            hint.setWordWrap(True);interaction.addWidget(hint)
            interaction=section(layout,'表情与角色')
            for key,title in [('resource_face','显示表情（收起与展开）'),('resource_face_interactive','表情互动（跟随、眨眼与按压）')]:
                self.fields[key]=check(title,cfg[key]);interaction.addWidget(self.fields[key])
            face_form=QFormLayout();interaction.addLayout(face_form)
            combo(face_form,'resource_face_mood','表情样式',list(zip(('靠近随机变化','默认','开心','眨眼','爱心','星星眼','害羞','嘟嘴','眯眼'),('random','default','happy','wink','love','star','shy','pout','squint'))),cfg['resource_face_mood'],self.fields)
            auto_switch = check('定时切换表情', cfg['resource_face_auto_switch'])
            self.fields['resource_face_auto_switch'] = auto_switch
            face_form.addRow(auto_switch)
            spin(face_form, 'resource_face_switch_minutes', '切换间隔（分钟）', *FACE_SWITCH_RANGE,
                 cfg['resource_face_switch_minutes'], self.fields)
            interval = self.fields['resource_face_switch_minutes']
            interval.setEnabled(auto_switch.isChecked())
            auto_switch.toggled.connect(interval.setEnabled)
            spin(face_form,'resource_face_scale','表情大小（%）',60,130,cfg['resource_face_scale'],self.fields)
            from face_role_controls import add_role_controls
            self.fields['resource_face_role']=add_role_controls(self,face_form,self.service.runtime,
                                                               self.status,cfg['resource_face_role'])
            layout.addStretch()

        def build_7():
            layout=page(7)
            daily=section(layout,'天气与空气质量')
            self.fields['resource_weather']=check('显示天气',cfg['resource_weather'])
            daily.addWidget(self.fields['resource_weather'])
            daily.addWidget(QLabel('天气城市（最多 6 个，以逗号分隔）'))
            self.weather_cities=QLineEdit('，'.join(cfg['resource_weather_cities']));self.weather_cities.setAccessibleName('天气城市');daily.addWidget(self.weather_cities)
            weather_form=QFormLayout();daily.addLayout(weather_form)
            combo(weather_form,'resource_weather_days','天气范围',[('昨天、今天、明天',3),('未来一周（今天起 7 天）',7),('仅今天',1),('今天、明天',2),('今天起 4 天',4),('今天起 5 天',5),('今天起 6 天',6)],cfg['resource_weather_days'],self.fields)
            combo(weather_form,'resource_air_source','空气质量来源',[('Open-Meteo 自动','auto'),('CAMS 全球小时数据','cams'),('和风天气','qweather')],cfg['resource_air_source'],self.fields)
            from weather_connection import edit_connection
            daily.addWidget(button('和风天气连接…',lambda:edit_connection(self,self.service)))
            daily=section(layout,'新闻订阅')
            self.fields['resource_news']=check('显示新闻订阅',cfg['resource_news']);daily.addWidget(self.fields['resource_news'])
            daily.addWidget(QLabel('RSS / Atom 订阅链接（每行一个，最多 5 个）'))
            from PyQt5.QtWidgets import QPlainTextEdit
            self.news_feeds=QPlainTextEdit('\n'.join(cfg['resource_news_feeds']))
            self.news_feeds.setAccessibleName('新闻订阅链接')
            self.news_feeds.setFixedHeight(82)
            daily.addWidget(self.news_feeds)
            layout.addStretch()

        def build_8():
            layout=page(8)
            placement=section(layout,'胶囊栏目顺序')
            placement.addWidget(button('调整胶囊栏目顺序…',lambda:self.edit_order('resource_component_order',CAPSULE_PAGES)))
            hint=QLabel('已开启的组件可选择显示在胶囊或独立桌面卡片中。应用收纳卡片独立管理。')
            hint.setWordWrap(True);placement.addWidget(hint)
            for title,keys in PLACEMENT_GROUPS:
                placement=section(layout,title)
                form=QFormLayout();placement.addLayout(form)
                for key in keys:
                    label='番茄钟与喝水' if key=='pomodoro' else PLACED_COMPONENTS[key]
                    combo(form,key,label,[('收入资源胶囊','capsule'),('独立桌面卡片','desktop')],
                          component_location(cfg,key),self.location_fields)
            layout.addStretch()

        def build_9():
            from resource_calendar_settings import CalendarAccounts

            layout=page(9)
            sounds=section(layout,'声音')
            key='resource_reminder_sound'
            self.fields[key]=check('播放提示音',cfg[key]);sounds.addWidget(self.fields[key])
            agenda=section(layout,'日程与账号')
            self.fields['resource_agenda']=check('显示日程',cfg['resource_agenda'])
            agenda.addWidget(self.fields['resource_agenda'])
            key='resource_alert_agenda'
            self.fields[key]=check('收起时显示日程提醒',cfg[key]);agenda.addWidget(self.fields[key])
            agenda.addWidget(CalendarAccounts(self.service))
            agenda.addWidget(button('日程账号接入…',self.agenda_connections))
            timers=section(layout,'专注与喝水')
            self.fields['resource_pomodoro']=check('显示番茄钟与喝水提醒',cfg['resource_pomodoro'])
            timers.addWidget(self.fields['resource_pomodoro'])
            for key,title in (('resource_alert_focus','收起时显示专注计时与完成提醒'),
                              ('resource_alert_water','收起时显示喝水提醒')):
                self.fields[key]=check(title,cfg[key]);timers.addWidget(self.fields[key])
            layout.addStretch()

        self.builders=[build_0,build_1,build_2,build_3,build_4,build_5,build_6,build_7,build_8,build_9]
        self.tabs.currentChanged.connect(self.show_page)
        self.nav.currentItemChanged.connect(self.navigate)
        self.show_page(0)

        footer=QHBoxLayout();self.status=QLabel();self.status.setWordWrap(True);footer.addWidget(self.status,1)
        footer.addWidget(button('关闭',self.reject));footer.addWidget(button('保存设置',self.commit,'primary'));box.addLayout(footer)
        from ui_style import compact_dialog
        compact_dialog(self)
        self.size_navigation()

    def size_navigation(self):
        scale = float(self.property('interfaceScale') or .7)
        self.nav.fit_density()
        heading = QFont(self.nav.font())
        heading.setPixelSize(max(10,round(13*scale)))
        heading.setWeight(QFont.DemiBold)
        for row in range(self.nav.count()):
            item = self.nav.item(row)
            if item.data(Qt.UserRole) is None:
                item.setFont(heading)
                item.setSizeHint(QSize(0,max(17,round((27 if row else 22)*scale))))

    def navigate(self, item, _previous):
        if item is not None:
            index=item.data(Qt.UserRole)
            if index is not None:
                self.tabs.setCurrentIndex(index)

    def install_driver(self):
        from pawnio_setup import launch
        try:launch();self.status.setText('已打开内置安装程序。')
        except (OSError,ValueError) as error:self.status.setText(str(error))

    def gateway_connections(self):
        from resource_gateway_settings import edit_gateways
        edit_gateways(self.service,self)

    def agenda_connections(self):
        from resource_calendar_settings import show_connections
        show_connections(self,self.service)

    def edit_peripherals(self,count):
        from resource_peripheral_settings import PeripheralSettings
        service=self.service
        profiles=self.orders.get('resource_peripheral_profiles',service.cfg['resource_peripheral_profiles'])
        service.peripheral_editing=True
        service.sync_peripherals()
        try:
            dialog=PeripheralSettings(self,profiles)
            try:
                if dialog.exec_()==QDialog.Accepted:
                    self.orders['resource_peripheral_profiles']=dialog.profiles
                    n=len(dialog.profiles)
                    count.setText(f'已添加 {n} 台设备' if n else '尚未添加 2.4G 外设')
            finally:
                dialog.deleteLater()
        finally:
            service.peripheral_editing=False
            if not service.closed:service.sync_peripherals()

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
                if key == 'resource_compact_order':
                    self.orders['resource_compact_pinned'] = list(self.orders[key])
        finally:
            dialog.deleteLater()

    def commit(self):
        for index in self.loaded:
            self.snapshot_page(index)
        changes = dict(self.orders)
        for draft in self.drafts.values():
            changes.update(draft['stores']['fields'])
        if 8 in self.drafts:
            locations=dict(self.service.cfg['resource_component_locations'])
            for key,value in self.drafts[8]['stores']['location_fields'].items():
                if value!=component_location(self.baseline,key):locations[key]=value
            changes['resource_component_locations']=locations
        if 7 in self.drafts:
            import re
            from resource_weather import clean_cities
            from content_sources import clean_feeds
            try:
                changes['resource_weather_cities']=clean_cities([s.strip() for s in re.split('[,，;；]',self.drafts[7]['text']) if s.strip()],True)
                changes['resource_news_feeds']=clean_feeds(self.drafts[7]['feeds'].split(),True)
            except ValueError as error:self.status.setText(str(error));return False
        for index,key,name in [(1,'resource_task_metrics','task_fields'),(1,'resource_task_media_parts','task_media_fields'),
                               (2,'resource_compact_metrics','compact_fields'),
                               (3,'resource_ai_providers','ai_fields')]:
            if index in self.drafts:
                selected = self.drafts[index]['stores'][name]
                # Preserve the saved priority of checked items across tab changes.
                order = dict.fromkeys([*self.baseline[key], *selected])
                changes[key] = [item for item in order if selected.get(item)]
        if 2 in self.drafts:
            pins=changes.get('resource_compact_pinned',self.baseline['resource_compact_pinned'])
            previous=set(self.baseline['resource_compact_metrics'])
            added=[key for key in changes['resource_compact_metrics'] if key in PINNABLE and key not in previous]
            added.extend(key for key,option in COMPACT_CONTENT.items() if changes.get(option) and not self.baseline[option])
            if added:
                changes['resource_compact_pinned']=list(dict.fromkeys([*pins,*added]))
        if 5 in self.drafts:
            from resource_status import default_limit
            thresholds=self.drafts[5]['stores']
            changes['resource_limits']={k:value for k,value in thresholds['limit_fields'].items() if value!=default_limit(k)}
            try:changes['resource_weather_thresholds']=clean_weather_thresholds([thresholds['weather_threshold_fields'][i] for i in range(4)],True)
            except ValueError as error:self.status.setText(str(error));return False
        if len(changes.get('resource_ai_providers',[]))>7:self.status.setText('最多同时显示 7 个 AI 工具。');return False
        if 4 in self.drafts:
            changes['resource_tints']=dict(self.tints)
            custom=dict(self.drafts[4]['stores']['custom_fields'], color=self.drafts[4]['text'].strip().lower())
            if changes['resource_background']=='custom' or self.service.cfg['resource_appearance'] or custom!=(self.baseline['resource_appearance'] or background(self.baseline)):
                try:changes['resource_appearance']=clean_background(custom,True)
                except ValueError:
                    self.status.setText('请输入 #RRGGBB 颜色值，或点击「默认」。');return False
        changes={k:v for k,v in changes.items() if v!=self.baseline.get(k)}
        if changes.get('resource_capsule_taskbar'):changes['resource_collapsed']=True
        ok=self.service.set_options(**changes) if changes else True
        if ok:self.baseline.update(changes)
        self.status.setText('已保存。' if ok else '保存失败，请重试。')
        return ok
