from ui_style import compact_dialog, compact_px
"""Settings for existing upstream features; edits apply only on Save."""
import os
import copy
from contextlib import contextmanager
from weakref import proxy
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QFormLayout, QSpinBox, QCheckBox, QComboBox, QScrollArea, QApplication, QLineEdit, QColorDialog,
    QStackedWidget, QSizePolicy, QFileDialog)
from ui_style import (label, button, apply_theme, ModernComboBox, ModernSpinBox,
                      ModernCheckBox, SettingsHeader, SettingsGrip, ThemeSwatches)
from app_version import VERSION, AUTHOR, PROJECT_URL
from appearance_presets import DOCK_PRESETS, material_choices, select_material, COLOR_MODES
from settings_design import SettingsNavigation


class SettingsPages(QWidget):
    NAV_SYMBOLS = ('palette', 'panels', 'apps', 'startup', 'update', 'size', 'info')
    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        self.nav = SettingsNavigation()
        self.pages = QStackedWidget()
        layout.addWidget(self.nav)
        layout.addWidget(self.pages, 1)
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)

    def addTab(self, page, name):
        index = self.pages.addWidget(page)
        self.nav.add_page(name,self.NAV_SYMBOLS[index])
        if self.nav.currentRow() < 0: self.nav.setCurrentRow(0)

    def count(self): return self.pages.count()
    def currentIndex(self): return self.nav.currentRow()
    def setCurrentIndex(self, index): self.nav.setCurrentRow(index)

    def resizeEvent(self, event):
        self.nav.fit_density()
        super().resizeEvent(event)


from settings_layout import SETTINGS_MINIMUM, SETTINGS_SIZE, SettingsSizingMixin
from settings_profiles import AppearanceProfileMixin


class SettingsFields(dict):
    def __init__(self, dialog):
        super().__init__()
        self.dialog = proxy(dialog)

    def __missing__(self, key):
        if key not in self.dialog.catalog:
            raise KeyError(key)
        self.dialog.ensure_page(self.dialog.catalog[key][0])
        return dict.__getitem__(self, key)


class SettingsDialog(AppearanceProfileMixin,SettingsSizingMixin,QDialog):
    PAGE_ATTRIBUTES = {
        'dock_preset': 0,
        'dock_preview': 0,
        'overall_style': 0,
        'restore_style': 0,
        'taskbar_text_status': 0,
        'panel_preset': 1,
        'current_startup_path': 3,
        'startup_check': 3,
        'startup_path': 3,
        'startup_repair': 3,
        'startup_status': 3,
        'update_link': 4,
        'update_status': 4,
        'usage_page': 5,
        'config_recovery': 6,
        'config_status': 6,
        'project': 6,
        'transfer_status': 6,
    }
    PAGE_BUILDERS = ('build_appearance', 'build_panel', 'build_apps', 'build_running', 'build_updates', 'build_usage', 'build_info')

    def __init__(self, tray, api):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint | Qt.WindowMinimizeButtonHint)
        self.setObjectName('SettingsDialog')
        self.setProperty('compactDialog', True)
        self.tray, self.api = tray, api
        self._runtime_switch_keys=('panel_enabled','notes_enabled','clock_enabled','calendar_enabled','spectrum_enabled','daily_picture_enabled','flash_enabled','resource_enabled','resource_taskbar','resource_bt_tray','hide_tray','game_mode','fullscreen_detection')
        self._runtime_switch_baseline={key:tray.cfg[key] for key in self._runtime_switch_keys}
        self.fields = SettingsFields(self)
        self.import_candidate=None;self.import_path=None
        self.default_candidate = None
        self.applying_dock_preset = False
        self.setWindowTitle('设置 · 大肥鱼Dock')
        self.resize(*SETTINGS_SIZE)
        self.setMinimumSize(*SETTINGS_MINIMUM)
        body = QVBoxLayout(self)
        body.setContentsMargins(18, 12, 18, 12)
        body.setSpacing(12)
        self.header = SettingsHeader(self)
        self.create_size_selector()
        body.addWidget(self.header)
        search_row=QHBoxLayout()
        self.setting_query=QLineEdit();self.setting_query.setPlaceholderText('搜索设置，例如：圆角、自启、透明度')
        self.setting_query.setClearButtonEnabled(True);self.setting_query.returnPressed.connect(self.search_settings)
        search_row.addWidget(self.setting_query,1);search_row.addWidget(button('搜索',self.search_settings));body.addLayout(search_row)
        self.tabs = SettingsPages()
        body.addWidget(self.tabs, 1)
        from settings_catalog import PAGES, field_catalog
        self.catalog = field_catalog(api, tray.cfg)
        self._draft = {key: tray.cfg[key] for key in self.catalog}
        self._mounted = {}
        self._page_density = {}
        self._scroll_positions = {}
        self._suspended = False
        self.transfer_help = '导出已保存的应用、卡片、便签正文和偏好；导入先预览，保存后替换当前配置并保留一份导入前备份。应用和桌面文件仅保存路径引用。便签正文包含在导出文件中，请妥善保管。'
        self._transfer_message = self.transfer_help
        for name in PAGES:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            self.tabs.addTab(scroll, name)
        self.status = label('修改后保存，关闭不保存。', 'muted')
        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addWidget(self.status, 1)
        actions.addWidget(button('关闭', self.reject))
        self.save = button('保存设置', self.commit, 'primary')
        self.save.setDefault(True)
        actions.addWidget(self.save)
        self.grip = SettingsGrip(self)
        self.grip.setFixedSize(12, 18)
        self.grip.setAccessibleName('调整设置窗口大小')
        actions.addWidget(self.grip, 0, Qt.AlignBottom)
        body.addLayout(actions)
        runtime = getattr(tray, 'runtime', None)
        if runtime:
            runtime.updater.changed.connect(self.update_changed)
            runtime.panels.shared_settings_changed.connect(self.refresh_shared_panel_fields)
        self.load_profile(tray.cfg)
        compact_dialog(self)
        from idle_resources import watch
        watch(self)
        self.initialize_size_behavior()
        self.tabs.nav.currentRowChanged.connect(self.show_page)
        self.ensure_page(0)

    def __getattr__(self, name):
        page = self.PAGE_ATTRIBUTES.get(name)
        if page is not None and '_mounted' in self.__dict__:
            self.ensure_page(page)
            if name in self.__dict__:
                return self.__dict__[name]
        raise AttributeError(name)

    def ensure_page(self, index):
        if index < 0 or index in self._mounted:
            return
        from settings_design import group_form
        from settings_layout import apply_density, capture_density
        from ui_style import compact_widget_tree

        form = self.section(index)
        self._mounted[index] = ()
        getattr(self, self.PAGE_BUILDERS[index])(form)
        keys = tuple(key for key in self.fields if self.catalog[key][0] == index)
        self._mounted[index] = keys
        self.set_draft_values({key: self._draft[key] for key in keys})
        self.connect_profile_fields(keys)
        if index == 0:
            self.position_changed()
            self.sync_profile_selector()
        elif index == 3:
            self.check_startup()
        elif index == 4:
            runtime = getattr(self.tray, 'runtime', None)
            if runtime:
                self.update_changed(runtime.updater.message)
        elif index == 6:
            self.refresh_config_status()
        self.refresh_preset_names(self._draft)
        group_form(form, self)
        page = form.parentWidget()
        compact_widget_tree(page)
        reference = capture_density(page)
        self._page_density[index] = reference
        apply_density(reference, float(self.property('interfaceScale') or .7))
        scroll = self.tabs.pages.widget(index)
        scroll.verticalScrollBar().setValue(self._scroll_positions.get(index, 0))

    def unmount_page(self, index):
        keys = self._mounted.pop(index)
        for key in keys:
            field = self.fields.pop(key)
            self._draft[key] = self.field_value(key, field)
        scroll = self.tabs.pages.widget(index)
        self._scroll_positions[index] = scroll.verticalScrollBar().value()
        page = scroll.takeWidget()
        self._page_density.pop(index, None)
        for name, owner in self.PAGE_ATTRIBUTES.items():
            if owner == index:
                self.__dict__.pop(name, None)
        if page is not None:
            page.hide()
            page.deleteLater()

    def show_page(self, index):
        if index < 0 or self._suspended:
            return
        for previous in tuple(self._mounted):
            if previous != index:
                self.unmount_page(previous)
        self.ensure_page(index)
        page = self.__dict__.get('usage_page')
        if page is not None:
            page.refresh()

    @contextmanager
    def suspend_page(self):
        """Release the main editor's widgets and backing store for a modal editor."""
        index = self.tabs.currentIndex()
        self._suspended = True
        self.hide()
        for previous in tuple(self._mounted):
            self.unmount_page(previous)
        self.destroy()
        self._bound_settings_screen = False
        try:
            yield
        finally:
            self._suspended = False
            if not self.tray.runtime.closed:
                self.ensure_page(index)
                self.show()

    @staticmethod
    def field_value(key, field):
        if isinstance(field, QComboBox):
            return field.currentData()
        if isinstance(field, QSpinBox):
            return 100 - field.value() if key == 'transparency' else field.value()
        if isinstance(field, QLineEdit):
            return field.text().strip()
        return field.isChecked()

    @staticmethod
    def change_signal(field):
        if isinstance(field, QComboBox):
            return field.currentIndexChanged
        if isinstance(field, QSpinBox):
            return field.valueChanged
        if isinstance(field, QLineEdit):
            return field.textChanged
        return field.toggled

    def draft_values(self):
        return dict(self._draft, **{key: self.field_value(key, field) for key, field in self.fields.items()})

    def set_draft_values(self, changes):
        for key, value in changes.items():
            if key not in self.catalog:
                continue
            self._draft[key] = value
            field = self.fields.get(key)
            if field is None:
                continue
            blocked = field.blockSignals(True)
            try:
                if key in ('dock_material', 'panel_material'):
                    select_material(field, value)
                elif key == 'panel_face_role':
                    field.select(value)
                elif isinstance(field, QComboBox):
                    field.setCurrentIndex(max(0, field.findData(value)))
                elif isinstance(field, QSpinBox):
                    field.setValue(100 - value if key == 'transparency' else value)
                    if isinstance(field, ModernSpinBox):
                        field.sync_steps()
                elif isinstance(field, QLineEdit):
                    field.setText(value)
                else:
                    field.setChecked(bool(value))
            finally:
                field.blockSignals(blocked)
        from settings_design import NumericControl
        for control in self.findChildren(NumericControl):
            control.slider.setValue(control.spin.value())

    def add_field(self, form, key, visible=True):
        _, title, kind, options = self.catalog[key]
        if kind == 'combo':
            self.combo(form, key, title, options, visible=visible)
        elif kind == 'number':
            self.number(form, key, title, *options)
        else:
            getattr(self, kind)(form, key, title)

    def build_appearance(self, appearance):
        tray, api = self.tray, self.api
        from settings_design import section_marker
        section_marker(appearance, '默认设置')
        defaults = QHBoxLayout()
        defaults.addWidget(button('使用默认设置', self.stage_defaults))
        defaults.addWidget(label('载入默认配置，保存后生效。', 'muted'), 1)
        appearance.addRow(defaults)
        self.create_profile_controls(appearance)
        section_marker(appearance,'Dock 材质与配色')
        self.dock_preset = ModernComboBox()
        self.dock_preset.addItem('自定义')
        self.dock_preset.addItems([name for name, _ in DOCK_PRESETS])
        appearance.addRow(self.field_label('主题预设'), self.dock_preset)
        self.add_field(appearance, 'dock_material')
        self.add_field(appearance, 'theme')
        self.add_field(appearance, 'theme_color')
        section_marker(appearance,'质感与尺寸')
        self.add_field(appearance, 'dock_highlight')
        self.add_field(appearance, 'transparency')
        self.add_field(appearance, 'blur_px')
        self.add_field(appearance, 'icon_size')
        self.add_field(appearance, 'glass')
        self.add_field(appearance, 'clear_background')
        self.fields['clear_background'].setToolTip('仅保留图标与文字，不绘制玻璃背景。')
        self.add_field(appearance, 'blur_mode')
        self.add_field(appearance, 'magnify')
        self.add_field(appearance, 'motion_enabled')
        self.fields['motion_enabled'].setToolTip('悬停、展开和切换时短暂流动，静止后停止；壁纸取样位置保持不变。')
        section_marker(appearance,'Dock 扩展')
        from settings_design import ResponsiveFields
        extras=ResponsiveFields()
        for key,title in [('dock_reflections','图标倒影'),('dock_clock','时间'),('dock_quick_settings','九宫格'),('dock_add_button','＋ 添加')]:
            control=ModernCheckBox(title);self.fields[key]=control;extras.add(control)
        appearance.addRow(extras)
        self.add_field(appearance, 'bump_level')
        layout = appearance
        section_marker(layout,'停靠与交互')
        self.add_field(layout, 'position')
        self.add_field(layout, 'custom_bottom')
        self.add_field(layout, 'bottom_margin')
        self.add_field(layout, 'layer')
        self.add_field(layout, 'show_name')
        self.add_field(layout, 'sep_split')
        self.add_field(layout, 'lang')
        section_marker(layout,'屏幕圆角')
        self.add_field(layout, 'screen_corners')
        self.fields['screen_corners'].setToolTip('手动暂停桌面组件时隐藏，圆角区域允许鼠标穿透。')
        self.add_field(layout, 'corner_radius')

        section_marker(appearance, 'Windows 任务栏')
        self.add_field(appearance, 'taskbar_mode')
        self.add_field(appearance, 'taskbar_text_mode')
        self.taskbar_text_status=label('文字明暗联动 Windows 模式，开始菜单等系统区域也会改变；普通应用配色保留。退出后恢复原设置。','muted')
        appearance.addRow(self.taskbar_text_status)
        self.add_field(appearance, 'taskbar_color')
        self.add_field(appearance, 'taskbar_opacity')
        self.add_field(appearance, 'taskbar_blur')
        taskbar = getattr(getattr(tray, 'runtime', None), 'taskbar', None)
        if taskbar:
            taskbar_status = label(taskbar.status, 'muted')
            appearance.addRow(taskbar_status)
            taskbar.changed.connect(taskbar_status.setText)
            self.action_row(appearance,'应用状态',button('重试任务栏效果',taskbar.retry))
            if taskbar.payload:
                def installed(success, message):
                    from PyQt5 import sip
                    if sip.isdeleted(taskbar_status):
                        return
                    taskbar_status.setText(message)
                    setup.setEnabled(True)
                    if success:
                        for key in ('taskbar_mode', 'taskbar_color', 'taskbar_opacity', 'taskbar_blur'):
                            self.fields[key].setEnabled(True)

                def install_taskbar():
                    if taskbar.install_offline(installed):
                        setup.setEnabled(False)
                        taskbar_status.setText('正在安装任务栏组件和缺失的依赖…')

                setup = button('安装或修复离线组件', install_taskbar)
                appearance.addRow(setup)
            if taskbar.backend is None:
                import sys
                if sys.platform == 'win32' and sys.getwindowsversion().build >= 22000:
                    from update_sources import DEFAULT_SOURCE
                    download = label(f'<a href="{DEFAULT_SOURCE}">下载完整安装包并安装任务栏效果组件</a>', 'muted')
                    download.setOpenExternalLinks(True)
                    appearance.addRow(download)
                for key in ('taskbar_mode', 'taskbar_color', 'taskbar_opacity', 'taskbar_blur'):
                    self.fields[key].setEnabled(False)

        self.fields['position'].currentIndexChanged.connect(self.position_changed)
        self.dock_preset.currentIndexChanged.connect(self.apply_dock_preset)
        self.fields['dock_material'].currentIndexChanged.connect(self.material_changed)
        for key in DOCK_PRESETS[0][1]:
            self.change_signal(self.fields[key]).connect(self.customize_dock)
        from settings_design import DockPreview
        self.dock_preview = DockPreview(self)
        appearance.insertRow(4, self.dock_preview)

    def build_panel(self, panel):
        tray, api = self.tray, self.api
        from settings_design import section_marker
        panel.addRow(label('外观与收起选项应用到全部卡片，位置和内容分别保存。', 'muted'))
        section_marker(panel,'显示与分类')
        self.add_field(panel, 'panel_enabled')
        self.add_field(panel, 'desktop_auto_sort')
        section_marker(panel,'卡片材质与配色')
        from appearance_presets import PANEL_PRESETS
        self.panel_preset=ModernComboBox();self.panel_preset.addItem('自定义')
        self.panel_preset.addItems([name for name,_ in PANEL_PRESETS])
        panel.addRow(self.field_label('主题预设'),self.panel_preset)
        self.panel_preset.currentIndexChanged.connect(self.apply_panel_preset)
        self.add_field(panel, 'card_design', visible=False)
        self.add_field(panel, 'panel_material')
        self.add_field(panel, 'panel_theme')
        self.add_field(panel, 'panel_color')
        self.add_field(panel, 'panel_highlight')
        self.add_field(panel, 'panel_opacity')
        self.add_field(panel, 'panel_blur')
        section_marker(panel,'收起与桌面交互')
        self.add_field(panel, 'panel_locked')
        self.add_field(panel, 'card_snap')
        self.add_field(panel, 'card_snap_distance')
        self.fields['card_snap_distance'].setToolTip('松手时检查与屏幕边缘、相邻卡片的距离。')
        self.add_field(panel, 'panel_auto_hide')
        self.add_field(panel, 'panel_expand_mode')
        self.add_field(panel, 'panel_face')
        self.add_field(panel, 'panel_face_interactive')
        self.add_field(panel, 'panel_face_mood')
        self.add_field(panel, 'panel_face_scale')
        self.add_field(panel, 'panel_face_role')
        self.add_field(panel, 'panel_collapse_style')
        self.add_field(panel, 'panel_capsule_ratio')
        self.add_field(panel, 'desktop_icon_mode')
        self.add_field(panel, 'desktop_middle_toggle')
        self.fields['desktop_middle_toggle'].setToolTip('仅点击 Windows 桌面时触发；滚动滚轮、点击任务栏、卡片或其他软件均不触发。')
        self.fields['desktop_icon_mode'].setToolTip('同时显示时可拖入桌面图标；隐藏全部只影响桌面图标视图，不修改文件属性。')
        self.fields['panel_material'].setToolTip('材质控制质感，颜色模式控制明暗，主题色控制配色；全部桌面卡片同步。')
        self.fields['panel_capsule_ratio'].setToolTip('相对于展开宽度，最窄180像素；全部桌面卡片同步，方条保持展开宽度。')
        section_marker(panel,'分组与尺寸')
        self.action_row(panel,'面板管理',button('新建面板',lambda:self.tray.runtime.panels.new_panel()),button('分组与合并',lambda:self.tray.runtime.panels.manage_groups()))
        panel.addRow(label('支持默认分类、自定义格式与多个合并组，文件只保存引用。','muted'))

        scale=ModernSpinBox();scale.setRange(50,150);scale.setAccessibleName('卡片整体缩放（%）');self.fields['card_scale']=scale
        self.action_row(panel,'卡片缩放（%）',scale,button('尺寸与文字…',lambda:self.tray.runtime.open_card_sizing()))
        panel.addRow(label('标题字号同步；便签正文单独设置。宽高可自由拖动，同一合并组共用尺寸。','muted'))
        section_marker(panel,'桌面组件')
        self.component_row(panel, 'clock_enabled', '桌面时钟', button('时钟设置', lambda:self.tray.runtime.clock.open_settings()))
        self.component_row(panel, 'calendar_enabled', '桌面日历', button('日历设置', lambda:self.tray.runtime.calendar.open_settings()))
        self.add_field(panel, 'spectrum_enabled')
        self.add_field(panel, 'spectrum_style')
        self.add_field(panel, 'spectrum_color_mode')
        self.add_field(panel, 'spectrum_mono_color')
        self.add_field(panel, 'daily_picture_enabled')
        self.add_field(panel, 'daily_picture_material')
        self.add_field(panel, 'daily_picture_color')
        self.add_field(panel, 'daily_picture_source')
        self.add_field(panel, 'daily_picture_interval')
        def choose_picture(folder=False):
            from daily_picture_card import choose_local
            choose_local(tray.runtime,folder=folder)
        self.action_row(panel,'本地图片',button('选择图片…',lambda:choose_picture()),
                        button('选择文件夹…',lambda:choose_picture(True)))
        self.fields['spectrum_enabled'].setToolTip('跟随默认播放设备的声音。拖动频谱移动，拖右下角调整大小，右键可切换样式或锁定。')
        self.action_row(panel,'自定义桌面卡片',button('原生卡片编辑器…',lambda:self.tray.runtime.open_custom_cards()))
        self.component_row(panel, 'notes_enabled', '便签卡片', button('新建便签', self.new_note), button('管理与搜索', lambda:self.tray.runtime.notes.manage()))
        self.add_field(panel, 'note_style')
        panel.addRow(label('便签支持文字格式、待办与自动保存，删除后可恢复。内容保存在本机，导出配置包含正文。','muted'))

        from flash_data import COLORS
        section_marker(panel,'闪念胶囊')
        self.component_row(panel,'flash_enabled','显示贴边胶囊',button('记一条',lambda:self.tray.runtime.flash.open(compose=True)),button('查看闪念',lambda:self.tray.runtime.flash.open()))
        self.add_field(panel, 'flash_palette')
        self.add_field(panel, 'flash_color')
        from flash_view import color_icon
        for index,key in enumerate(COLORS):self.fields['flash_color'].setItemIcon(index,color_icon(key))
        self.add_field(panel, 'flash_side')
        self.add_field(panel, 'flash_edge_hide')
        self.add_field(panel, 'flash_drop')
        self.add_field(panel, 'flash_auto_hide')
        self.add_field(panel, 'flash_delay')

        section_marker(panel,'资源胶囊')
        self.component_row(panel,'resource_enabled','显示资源胶囊',button('打开详情',lambda:self.tray.runtime.resources.open()),button('显示与采样…',lambda:self.tray.runtime.resources.settings()))
        self.add_field(panel, 'resource_taskbar')
        self.add_field(panel, 'resource_bt_tray')
        self.add_field(panel, 'resource_ai_tray')

        self.fields['panel_material'].currentIndexChanged.connect(self.panel_material_changed)

    def build_apps(self, apps):
        tray, api = self.tray, self.api
        from settings_design import section_marker
        section_marker(apps,'Dock 应用')
        apps.addRow(label('添加应用、Windows 工具或正在运行的软件，管理 Dock 中的快捷入口。', 'muted'))
        self.action_row(apps,'应用列表',button('批量管理…',self.open_batch))
        self.add_field(apps, 'reorder')
        self.add_field(apps, 'running_dots')
        apps.addRow(label('也可直接拖入应用或快捷方式。Dock 仅保存快捷引用，移除入口不会删除原文件。', 'muted'))

    def build_running(self, running):
        tray, api = self.tray, self.api
        from settings_design import section_marker
        section_marker(running,'后台运行')
        running.addRow(label('空闲时自动释放隐藏的收纳窗口、资源页和可重建缓存。', 'muted'))
        self.add_field(running, 'hide_tray')
        section_marker(running,'开机启动')
        self.add_field(running, 'autostart')
        running.addRow(label('启动后恢复上次的显示与运行状态。', 'muted'))
        self.startup_status = label('', 'muted')
        running.addRow(self.startup_status)
        self.startup_path = QLineEdit()
        self.startup_path.setReadOnly(True)
        self.startup_path.setAccessibleName('已登记的自启动路径')
        running.addRow(self.field_label('已登记路径'), self.startup_path)
        self.current_startup_path = QLineEdit(api.SCRIPT_PATH)
        self.current_startup_path.setReadOnly(True)
        self.current_startup_path.setAccessibleName('当前运行文件路径')
        running.addRow(self.field_label('当前运行路径'), self.current_startup_path)
        startup_actions = QHBoxLayout()
        self.startup_check = button('检测自启动路径', self.check_startup)
        self.startup_repair = button('修复并启用自启动', self.repair_startup)
        startup_actions.addWidget(self.startup_check)
        startup_actions.addWidget(self.startup_repair)
        startup_actions.addStretch()
        running.addRow('', startup_actions)
        running.addRow(label('修复会立即将当前运行版本登记为开机自启动，其他未保存的设置保持不变。', 'muted'))
        self.add_field(running, 'startup_priority')
        self.add_field(running, 'startup_delay')
        running.addRow(label('启用后在登录时尽早启动。设为 0 秒可免除程序等待；进程优先级作用于运行期间。', 'muted'))
        section_marker(running,'组件暂停')
        self.add_field(running, 'game_mode')
        self.add_field(running, 'fullscreen_detection')
        running.addRow(label('手动暂停会隐藏 Dock、卡片、胶囊、任务栏监控和圆角。全屏自动暂停独立启用，保留已置顶的任务栏监控，退出全屏后恢复。', 'muted'))

    def build_updates(self, updates):
        tray, api = self.tray, self.api
        from settings_design import section_marker
        section_marker(updates,'检查方式')
        self.add_field(updates, 'check_updates_on_start')
        self.add_field(updates, 'update_use_proxy')
        section_marker(updates,'更新来源')
        self.add_field(updates, 'update_source')
        updates.addRow(label('默认读取本项目 GitHub 正式 Release，优先打开 x64 安装包；也可填写 HTTPS 版本清单。安装更新由你确认。', 'muted'))
        self.update_status = label('已配置本项目安装包发布源，尚未检查', 'muted')
        updates.addRow(self.update_status)
        self.update_link=button('打开安装包 / 发布页',self.open_update_link);self.update_link.setEnabled(bool(getattr(getattr(self.tray,'runtime',None),'updater',None) and self.tray.runtime.updater.release_url))
        self.action_row(updates,'更新操作',button('检查更新',self.check_update),self.update_link)

    def build_usage(self, usage):
        tray, api = self.tray, self.api
        from settings_design import section_marker
        from usage_stats import UsagePage
        self.usage_page = UsagePage(self, usage)
        self.usage_page.refresh()

    def build_info(self, info):
        tray, api = self.tray, self.api
        from settings_design import section_marker
        info.addRow(label('大肥鱼Dock  ' + VERSION, 'section'))
        info.addRow(label('Windows 桌面整理与美化工具，集成快捷启动、分类收纳、资源监控和桌面组件。', 'muted'))
        info.addRow('维护作者', label(AUTHOR))
        info.addRow('平台', label('Windows 10 / 11 · x64'))
        info.addRow('第三方许可', label('PyQt5 GPLv3；Qt、Python 等许可见发行文件 licenses。'))
        self.project = label('')
        self.project.setOpenExternalLinks(False)
        self.project.linkActivated.connect(lambda url: self.tray.dock.launch(url))
        info.addRow('项目地址', self.project)
        section_marker(info, '整理工具')
        runtime=getattr(tray,'runtime',None)
        if runtime:
            self.action_row(info,'桌面整理',button('撤销上次整理',runtime.productivity.undo),button('布局方案…',runtime.productivity.open_layouts))
            self.action_row(info,'查找与修复',button('统一搜索…',runtime.productivity.open_search),button('失效入口检查…',runtime.productivity.open_references))
        section_marker(info, '本机数据与迁移')
        path = label(api.CONFIG_DIR)
        path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        path.setWordWrap(True)
        data_actions=QHBoxLayout();data_actions.addWidget(path,1);data_actions.addWidget(button('打开目录',self.open_data))
        info.addRow(self.field_label('数据目录'),data_actions)
        info.addRow(label('config.json 保存 Dock、桌面收纳记录与面板布局；dock.log 为日志。desktop_visibility.json 等保存桌面显示恢复记录，正常退出会清除。卸载默认保留个人配置。', 'muted'))
        transfer=QHBoxLayout()
        transfer.addWidget(button('导入配置…',self.import_configuration))
        transfer.addWidget(button('导出配置…',self.export_configuration))
        info.addRow('配置迁移',transfer)
        self.project.setText('<a href="%s">BigFishDockpro</a>' % PROJECT_URL)
        self.transfer_status=label(self._transfer_message,'muted')
        info.addRow(self.transfer_status)
        self.config_status=label('','muted');info.addRow(self.config_status)
        self.config_recovery=button('恢复默认配置…',self.recover_configuration)
        info.addRow(self.config_recovery)
        section_marker(info, '开源致谢')
        links = (
            '<a href="https://github.com/WKaleXD/iOS-style-Dock">iOS-style-Dock</a>',
            '<a href="https://github.com/MoFeng2223/BrimDeck">BrimDeck</a>',
            '<a href="https://github.com/deviffyy/OpenQuota">OpenQuota</a>',
            '<a href="https://github.com/AsamiAkito/wisland">Wisland</a>',
            '<a href="https://github.com/hmgvibe/FullWidget">FullWidget</a>',
        )
        credits = label('感谢 ' + '、'.join(links) + ' 等开源项目。完整致谢和许可见 README 与发行包。', 'muted')
        credits.setOpenExternalLinks(False)
        credits.linkActivated.connect(lambda url: self.tray.dock.launch(url))
        info.addRow(credits)

    def release_idle_resources(self):
        if self.isVisible() or self._suspended:return False
        if getattr(self.tray,'settings_dialog',None) is self:del self.tray.settings_dialog
        self.deleteLater()
        return True

    def component_row(self, form, key, title, *actions):
        row = QHBoxLayout()
        row.setSpacing(8)
        check = ModernCheckBox(title)
        self.fields[key] = check
        row.addWidget(check, 1)
        for action in actions:
            row.addWidget(action)
        form.addRow(row)

    def action_row(self,form,title,*widgets):
        container=QWidget();row=QHBoxLayout(container);row.setContentsMargins(0,0,0,0);row.setSpacing(8)
        caption=label(title, 'field-label');row.addWidget(caption)
        for widget in widgets:
            if isinstance(widget,QSpinBox):widget.setFixedWidth(106)
            row.addWidget(widget)
        row.addStretch()
        form.addRow(container)

    def section(self, index):
        from settings_catalog import PAGES
        scroll = self.tabs.pages.widget(index)
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(2, 8, 12, 12)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.addRow(label(PAGES[index], 'page-title'))
        scroll.setWidget(page)
        return form

    def field_label(self, title):
        widget = label(title)
        widget.setFixedWidth(130)
        widget.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        return widget

    def combo(self, form, key, title, options, visible=True):
        field = ModernComboBox(form.parentWidget())
        for name, value in options:
            field.addItem(name, value)
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
        container = QVBoxLayout()
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
        form.addRow(self.field_label(title), container)

    def face_role(self, form, key, title):
        from face_role_controls import add_role_controls
        self.fields[key] = add_role_controls(self, form, self.tray.runtime, self.status, self._draft[key])

    def panel_material_changed(self):
        if getattr(self,'_profile_loading',False) or self.applying_dock_preset:return
        from appearance_presets import material_design
        field=self.fields['card_design'];value=material_design(self.fields['panel_material'].currentData(),field.currentData())
        field.setCurrentIndex(field.findData(value))
        if self.fields['panel_material'].currentData()=='clear':
            self.fields['panel_opacity'].setValue(0);self.fields['panel_highlight'].setValue(0)
        elif self.fields['panel_opacity'].value()==0 and self.fields['panel_highlight'].value()==0:
            from appearance_presets import PANEL_PRESETS
            values=next((v for _,v in PANEL_PRESETS if v['material']==self.fields['panel_material'].currentData()),dict(opacity=38,highlight=45))
            self.fields['panel_opacity'].setValue(values['opacity']);self.fields['panel_highlight'].setValue(values['highlight'])

    def material_changed(self):
        if not self.applying_dock_preset and self.fields['dock_material'].currentData()=='clear':
            self.fields['clear_background'].setChecked(True)
            self.fields['transparency'].setValue(0);self.fields['dock_highlight'].setValue(0)
        if not self.applying_dock_preset and self.fields['dock_material'].currentData()!='clear' and self.fields['clear_background'].isChecked():
            self.fields['clear_background'].setChecked(False)
            if self.fields['transparency'].value()==0: self.fields['transparency'].setValue(38)
            if self.fields['dock_highlight'].value()==0: self.fields['dock_highlight'].setValue(45)

    def apply_dock_preset(self, index):
        if index <= 0: return
        self.applying_dock_preset = True
        for key, value in DOCK_PRESETS[index-1][1].items():
            field = self.fields[key]
            if isinstance(field, QComboBox): field.setCurrentIndex(field.findData(value))
            elif isinstance(field, QSpinBox): field.setValue(100-value if key == 'transparency' else value)
            elif isinstance(field, QLineEdit): field.setText(value)
            else: field.setChecked(value)
        self.applying_dock_preset = False

    def customize_dock(self, *args):
        if not self.applying_dock_preset: self.dock_preset.setCurrentIndex(0)

    def check(self, form, key, title):
        field = ModernCheckBox(title)
        self.fields[key] = field
        form.addRow('', field)

    def position_changed(self):
        self.fields['custom_bottom'].setEnabled(self.fields['position'].currentData() == 'custom')

    def refresh_shared_panel_fields(self):
        if self.import_candidate is not None:
            return
        from panel_preferences import CONFIG_KEYS
        self.set_draft_values({key: self.tray.cfg[key] for key in CONFIG_KEYS + ('card_design',)})
        self.refresh_preset_names(self.profile_candidate())

    def fill_fields(self, cfg):
        self._runtime_switch_baseline = {key: cfg[key] for key in self._runtime_switch_keys}
        self.set_draft_values({key: cfg[key] for key in self.catalog})
        if 'position' in self.fields:
            self.position_changed()
        self.refresh_preset_names(cfg)
        self.load_profile(cfg)

    def reveal(self):
        link_color = QApplication.palette().color(QPalette.Link).name()
        if 'project' in self.__dict__:
            self.project.setText('<a style="color:%s" href="%s">BigFishDockpro</a>' % (link_color, PROJECT_URL))
        cfg = self.tray.cfg
        self.import_candidate=None;self.import_path=None
        self.default_candidate = None
        self.set_transfer_message(self.transfer_help)
        self._manual_dimensions=list(cfg.get('settings_manual_size',[]));self._custom_density=cfg.get('settings_custom_density',100)
        self.fill_fields(cfg);self.adapt_interface()
        runtime = getattr(self.tray, 'runtime', None)
        if runtime:
            runtime.taskbar.reconcile_status()
            self.update_changed(runtime.updater.message)
        if 'startup_status' in self.__dict__:
            self.check_startup()
        self.status.setText('未保存的修改会在关闭时放弃。')
        self.refresh_config_status()
        self.move(QApplication.primaryScreen().availableGeometry().center() - self.rect().center())
        self.showNormal() if self.isMinimized() else self.show()
        self.raise_()
        self.activateWindow()

    def stage_defaults(self):
        from default_settings import apply, load
        try:
            preset = load()
            candidate = apply(self.tray.cfg, preset)
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.api.log('读取默认设置失败：'+str(error))
            self.status.setText('无法载入默认设置。')
            return False
        self.import_candidate = None
        self.import_path = None
        self.default_candidate = preset
        self._manual_dimensions = list(candidate['settings_manual_size'])
        self._custom_density = candidate['settings_custom_density']
        self.fill_fields(candidate)
        self.adapt_interface()
        self.set_transfer_message(self.transfer_help)
        self.status.setText('已载入默认设置，点击「保存设置」应用。')
        return True

    def import_configuration(self):
        path,_=QFileDialog.getOpenFileName(self,'导入 BigFishDockpro 配置','','JSON 配置 (*.json);;所有文件 (*)')
        if path:self.stage_import(path)

    def stage_import(self,path):
        try:
            from config_transfer import read_configuration
            cfg=read_configuration(path,self.api)
        except (OSError,ValueError,TypeError,RecursionError) as error:
            self.api.log('导入配置失败: '+str(error))
            self.status.setText('导入失败，当前配置未更改：'+str(error)[:80]);return False
        self.default_candidate = None
        self.fill_fields(cfg);self.import_candidate=cfg;self.import_path=path
        self.set_transfer_message('已载入 %d 个 Dock 入口、%d 个卡片、%d 张便签。保存后替换当前配置，关闭则放弃；文件仅保存路径引用，便签包含正文。'%(len(cfg['items']),len(cfg['desktop_panels']),len(cfg['sticky_notes'])))
        self.status.setText('配置已预览，尚未应用；点击“保存设置”生效。');return True

    def export_configuration(self):
        path,_=QFileDialog.getSaveFileName(self,'导出 BigFishDockpro 配置','BigFishDockpro-配置.json','JSON 配置 (*.json)')
        if path:self.export_to(path)

    def export_to(self,path):
        try:
            from config_transfer import export_configuration
            export_configuration(path,self.tray.cfg,self.api)
        except (OSError,ValueError,TypeError) as error:
            self.api.log('导出配置失败: '+str(error))
            self.status.setText('导出失败：'+str(error)[:80]);return False
        self.status.setText('已导出当前已保存的配置，未保存的修改未包含。');return True

    def apply_imported_state(self):
        self.api.set_lang(self.tray.cfg['lang'])
        self.tray.dock._sys_light=self.api.system_is_light()
        apply_theme(QApplication.instance(),self.tray.dock.is_light())
        runtime=getattr(self.tray,'runtime',None)
        if runtime:
            runtime.panels.shown=self.tray.cfg['panels_visible']
            runtime.was_dock_visible=self.tray.cfg['dock_visible']
            runtime.flash.sync(reload=True)
            runtime.apply_settings()
            if getattr(runtime,'notes',None):runtime.notes.reload()
            runtime.layout.apply()
            self.tray.dock.setVisible(self.tray.cfg['dock_visible'] and not runtime.game_active)
        else:self.tray.dock.reload()
        self.tray.dock.apply_layer()
        importer=getattr(self.tray,'importer',None)
        if importer and importer.dialog:importer.dialog.render()

    def reject(self):
        self.import_candidate=None;self.import_path=None
        self.default_candidate = None
        self.set_transfer_message(self.transfer_help)
        super().reject()

    def open_data(self):
        try:
            os.makedirs(self.api.CONFIG_DIR, exist_ok=True)
            from external_launch import startfile
            startfile(self.api.CONFIG_DIR)
        except OSError as error:
            self.api.log('打开数据目录失败: ' + str(error))
            self.status.setText('无法打开数据目录，请检查目录是否可用。')

    def commit(self):
        import re
        notes=getattr(getattr(self.tray,'runtime',None),'notes',None)
        if notes and not notes.flush():
            self.status.setText('便签尚未保存，请先保存便签后重试。');return
        flash=getattr(getattr(self.tray,'runtime',None),'flash',None)
        if flash and not flash.save_draft():
            self.status.setText('闪念草稿尚未保存，请先检查后重试。');return
        imported=self.import_candidate is not None
        defaults_selected = self.default_candidate is not None
        previous=copy.deepcopy(self.tray.cfg)
        cfg = copy.deepcopy(self.import_candidate) if imported else dict(self.tray.cfg)
        if defaults_selected:
            from default_settings import apply
            cfg = apply(self.tray.cfg, self.default_candidate)
        for key, value in self.draft_values().items():
            if not (imported or defaults_selected) and key in self._runtime_switch_baseline and value == self._runtime_switch_baseline[key]:
                continue
            cfg[key] = value
        cfg = self.stage_profile(cfg)
        cfg['settings_manual_size']=list(self._manual_dimensions)
        cfg['settings_custom_density']=self._custom_density
        for key in ('theme_color', 'panel_color', 'spectrum_mono_color', 'daily_picture_color'):
            if cfg[key] and not re.fullmatch(r'#[0-9a-fA-F]{6}', cfg[key]):
                self.status.setText('主题色请使用 #RRGGBB，或留空使用默认色。')
                return
            cfg[key] = cfg[key].lower()
        if cfg['update_source'] and not cfg['update_source'].startswith('https://'):
            self.status.setText('更新源必须是 HTTPS 发布地址或版本清单地址。')
            return
        backup=None
        if imported:
            runtime=getattr(self.tray,'runtime',None)
            importer=getattr(self.tray,'importer',None)
            dialog=importer.dialog if importer else None
            if dialog and (dialog.pending_add or dialog.pending_remove):
                self.status.setText('请先保存或关闭应用批量管理中的待保存改动，再保存导入配置。');return
            if runtime and (runtime.layout.pending or not runtime.layout.screens()):
                self.status.setText('显示器正在切换，请稍后再保存导入配置。');return
            try:
                from config_transfer import backup_before_import
                backup=backup_before_import(self.api,previous,self.import_path)
            except (OSError,ValueError) as error:
                self.api.log('配置备份失败: '+str(error))
                self.status.setText('无法备份当前配置，未导入：'+str(error)[:80]);return
        if not imported and cfg==previous:
            self.default_candidate = None
            self.status.setText('设置未变化，无需重复刷新。');return
        startup_changed = cfg['autostart'] != self.tray.cfg['autostart']
        if startup_changed and not self.api.set_autostart(cfg['autostart']):
            self.status.setText('启动项保存失败，设置尚未应用。请查看日志。')
            return
        recover=imported and self.api.config_status().get('blocked',False)
        saved=self.api.recover_config_defaults(cfg) if recover else self.api.save_config(cfg)
        self.refresh_config_status()
        if saved is False:
            if startup_changed and not self.api.set_autostart(self.tray.cfg['autostart']):
                self.status.setText('配置保存失败，且自启动恢复失败，请检测修复启动项。');return
            self.status.setText('配置保存失败，设置尚未应用。请检查数据目录权限。')
            return
        self.tray.cfg.update(cfg)
        self._profile_loading=True
        if imported or defaults_selected:
            action = '导入配置' if imported else '默认设置'
            try:self.apply_imported_state()
            except Exception as error:
                self.api.log(action+'应用失败: '+str(error))
                self.tray.cfg.clear();self.tray.cfg.update(previous)
                restored=self.api.save_config(previous)
                startup_restored=not startup_changed or self.api.set_autostart(previous['autostart'])
                ui_restored=True
                try:self.apply_imported_state()
                except Exception as rollback_error:
                    ui_restored=False;self.api.log('界面恢复失败: '+str(rollback_error))
                message=action+'应用失败，原配置已恢复，可重新尝试。' if ui_restored else '原配置已恢复，请重启程序以恢复界面。'
                if not startup_restored:message='原配置已恢复，但自启动恢复失败，请检测修复启动项。'
                self.status.setText(message if restored else '恢复配置失败，请检查数据目录。')
                return
            if imported:
                service=getattr(getattr(self.tray,'runtime',None),'productivity',None)
                if service:service.history.entries.clear();service.history.message='配置已导入，整理记录已清空'
                self.import_candidate=None;self.import_path=None
                self.set_transfer_message('导入已保存。导入前备份：'+backup.name+'；可从数据目录重新导入恢复。')
            self.default_candidate = None
        else:
            from settings_effects import apply_changes
            apply_changes(self.tray,self.api,previous)
        self._runtime_switch_baseline = {key: self.tray.cfg[key] for key in self._runtime_switch_keys}
        self.set_draft_values(self._runtime_switch_baseline)
        self.load_profile(self.tray.cfg)
        self.refresh_preset_names(self.tray.cfg)
        if 'startup_status' in self.__dict__:
            self.check_startup()
        self.status.setText('设置已保存并生效，可继续调整。')
        taskbar=getattr(getattr(self.tray,'runtime',None),'taskbar',None)
        error=getattr(taskbar,'error','') or getattr(getattr(taskbar,'text',None),'error','')
        if error:self.status.setText(error)

    def check_startup(self):
        from startup_service import inspect_startup
        result = inspect_startup(self.api)
        if 'startup_status' not in self.__dict__:
            return result
        self.startup_status.setText(result['message'])
        self.startup_path.setText(result['path'] or '未登记')
        self.startup_path.setCursorPosition(0)
        self.startup_path.setToolTip(str(result['command']))
        self.current_startup_path.setText(self.api.SCRIPT_PATH)
        self.current_startup_path.setCursorPosition(0)
        self.current_startup_path.setToolTip(result['expected'])
        return result

    def repair_startup(self):
        from startup_service import repair_startup
        success, message = repair_startup(self.api, self.tray.cfg)
        if success:
            self.tray.cfg['autostart'] = True
            self.fields['autostart'].setChecked(True)
        self.check_startup()
        self.startup_status.setText(message)
        self.status.setText(message)

    def new_note(self):
        identity=self.tray.runtime.notes.new()
        if identity:self.fields['notes_enabled'].setChecked(True)

    def open_batch(self):
        runtime = getattr(self.tray, 'runtime', None)
        if runtime:
            runtime.show_batch()
        else:
            self.tray.importer.show()

    def check_update(self):
        if self.fields['update_source'].text().strip() != self.tray.cfg['update_source'] or self.fields['update_use_proxy'].isChecked() != self.tray.cfg['update_use_proxy']:
            self.update_status.setText('请先保存更新设置，再执行检查。')
            return
        if hasattr(self.tray, 'runtime'):
            self.tray.runtime.updater.check()

    def update_changed(self, message):
        if 'update_status' not in self.__dict__:
            return
        self.update_status.setText(message)
        self.update_link.setEnabled(bool(self.tray.runtime.updater.release_url))

    def open_update_link(self):
        if hasattr(self.tray, 'runtime') and self.tray.runtime.updater.release_url:
            self.tray.dock.launch(self.tray.runtime.updater.release_url)

    def search_targets(self):
        from settings_catalog import targets
        return targets(self.catalog)

    def search_settings(self):
        dialog=self.tray.runtime.productivity.open_search()
        dialog.scope.setCurrentIndex(dialog.scope.findData('settings'));dialog.query.setText(self.setting_query.text());dialog.refresh();dialog.query.setFocus()

    def focus_setting(self,key):
        runtime=self.tray.runtime
        actions={'@clock':runtime.clock.open_settings,'@calendar':runtime.calendar.open_settings,'@notes':runtime.notes.manage,'@groups':runtime.panels.manage_groups,'@layouts':runtime.productivity.open_layouts,'@references':runtime.productivity.open_references}
        if key in actions:actions[key]();return
        if key not in self.catalog:
            return
        page = self.catalog[key][0]
        if page >= 0:
            self.tabs.setCurrentIndex(page)
        field = self.fields[key]
        if page >= 0:
            scroll = self.tabs.pages.widget(page)
            QApplication.processEvents()
            scroll.ensureWidgetVisible(field, 12, 36)
        field.setFocus(Qt.ShortcutFocusReason)

    def set_transfer_message(self, message):
        self._transfer_message = message
        status = self.__dict__.get('transfer_status')
        if status is not None:
            status.setText(message)

    def refresh_config_status(self):
        if 'config_status' not in self.__dict__:
            return
        status=self.api.config_status()
        self.config_status.setText(status.get('message',''))
        self.config_status.setVisible(bool(status.get('message')))
        self.config_recovery.setVisible(bool(status.get('blocked')))

    def recover_configuration(self):
        from PyQt5.QtWidgets import QMessageBox
        if QMessageBox.question(self,'恢复默认配置','当前配置无法读取。恢复默认将保留异常原件，重新建立应用入口与布局配置。\n如果有导出备份，建议先从备份恢复。是否恢复默认？',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        if self.api.recover_config_defaults():
            previous=copy.deepcopy(self.tray.cfg);candidate=self.api.load_config();self.tray.cfg.clear();self.tray.cfg.update(candidate)
            self.apply_imported_state();self.fill_fields(self.tray.cfg);self.refresh_config_status();self.status.setText('默认配置已恢复，异常原件已保留。')
            service=getattr(getattr(self.tray,'runtime',None),'productivity',None)
            if service:service.history.entries.clear();service.history.message='配置已恢复，整理记录已清空'
        else:self.refresh_config_status();self.status.setText('无法保留异常配置，未恢复默认。请检查数据目录。')
