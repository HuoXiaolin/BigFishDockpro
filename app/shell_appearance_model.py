"""Bounded preferences and native XAML rules for the existing Windows flyouts."""
import re
from functools import lru_cache
from typing import NamedTuple
from appearance_presets import APPEARANCE_SOURCES, DEFAULT_PANEL_STYLE, dock_appearance
from background_contrast import blend, foreground, rgb

KINDS = ('start', 'notifications')
NOTIFICATION_PARTS = (('quick', '快速设置'), ('media', '媒体控制'), ('toast', '通知弹窗'),
                      ('calendar', '日历'), ('tray_overflow', '托盘收纳'), ('taskbar_menu', '任务栏右键菜单'))
SOURCES = [APPEARANCE_SOURCES[0], ('跟随系统', 'system'), APPEARANCE_SOURCES[1]]
TEXT_MODES = [('自动调整', 'auto'), ('跟随系统', 'system'), ('自定义 · 白色', 'white'), ('自定义 · 黑色', 'black')]
START_STYLES = [('系统默认', False), ('Windows 11 · 玻璃网格', True)]
START_SHADOWS = ('DropShadow', 'StartDropShadow', 'RootGridDropShadow', 'RightCompanionDropShadow')
START_MENU_SIZE = (608, 552)
START_PIN_COLUMNS = 4
START_PIN_CELL = (88, 84)
START_INSET = 16
START_GAP = 16
START_PAGER = 10
START_FOLDER_COLUMNS = 3
START_FOLDER_CELL = (76, 84)


class StartLayout(NamedTuple):
    width: int
    height: int
    columns: int
    cell_width: int

    @property
    def apps_width(self):
        return self.width - 2 * START_INSET - START_GAP - self.columns * self.cell_width - START_PAGER


def start_layout(work_area=None):
    width, height = START_MENU_SIZE
    if work_area is not None:
        # The native frame keeps an additional 12 DIPs on each edge.
        width = min(width, max(1, work_area[0] - 24))
        height = min(height, max(1, work_area[1] - 24))
    pin_space = width - 2 * START_INSET - START_GAP - START_PAGER - 176
    columns = max(1, min(START_PIN_COLUMNS, pin_space // 76))
    cell_width = max(76, min(START_PIN_CELL[0], pin_space // columns))
    return StartLayout(width, height, columns, cell_width)


def _display_start_layout():
    from PyQt5.QtGui import QGuiApplication
    if not isinstance(QGuiApplication.instance(), QGuiApplication):
        return start_layout()
    # Start and Search share one frame. A display can disappear between Qt's
    # screen enumeration and geometry query, including during sign-in.
    try:
        areas = [screen.availableGeometry() for screen in QGuiApplication.screens()]
    except RuntimeError:
        return start_layout()
    areas = [area for area in areas if area.isValid()]
    if not areas:
        return start_layout()
    return start_layout((min(area.width() for area in areas), min(area.height() for area in areas)))


DEFAULTS = {}
for _kind in KINDS:
    DEFAULTS.update({f'shell_{_kind}_{key}': value for key, value in dict(
        enabled=False, source='app', material='crystal', theme='auto', color='#deedf9',
        opacity=DEFAULT_PANEL_STYLE['opacity'], blur=DEFAULT_PANEL_STYLE['blur'],
        highlight=DEFAULT_PANEL_STYLE['highlight'], text_mode='auto').items()})
for _part, _ in NOTIFICATION_PARTS:
    DEFAULTS['shell_notifications_' + _part] = True


def normalize(cfg):
    from appearance_presets import MATERIALS
    cfg.pop('shell_start_layout', None)
    for key, default in DEFAULTS.items():
        value = cfg.get(key, default)
        if type(default) is bool:
            value = value if type(value) is bool else default
        elif type(default) is int:
            value = max(0, min(50 if key.endswith('_blur') else 100, value)) if type(value) is int else default
        elif key.endswith('_color'):
            value = value if isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value) else default
        else:
            allowed = {'source': {v for _, v in SOURCES},
                       'theme': {'auto', 'light', 'dark'}, 'material': {v for _, v in MATERIALS},
                       'text_mode': {v for _, v in TEXT_MODES}}
            value = value if isinstance(value, str) and value in allowed[key.split('_', 2)[2]] else default
        cfg[key] = value
    return cfg


def catalog(start_page, notification_page):
    from appearance_presets import MATERIALS, COLOR_MODES
    fields = {
        'shell_start_enabled': (start_page, '菜单样式', 'combo', START_STYLES),
        'shell_notifications_enabled': (notification_page, '美化通知与快捷面板', 'check', None),
    }
    for kind, page in (('start', start_page), ('notifications', notification_page)):
        prefix = 'shell_' + kind + '_'
        fields.update({prefix + key: (page, title, widget, options) for key, title, widget, options in (
            ('source', '外观来源', 'combo', SOURCES), ('material', '材质', 'combo', MATERIALS),
            ('theme', '明暗模式', 'combo', COLOR_MODES), ('text_mode', '字体颜色', 'combo', TEXT_MODES),
            ('color', '背景色', 'color', None),
            ('opacity', '底色不透明度（%）', 'number', (0, 100)), ('blur', '模糊强度', 'number', (0, 50)),
            ('highlight', '高光（%）', 'number', (0, 100)))})
    for part, title in NOTIFICATION_PARTS:
        fields['shell_notifications_' + part] = (notification_page, title, 'check', None)
    return fields


@lru_cache(maxsize=32)
def _dock_surface(material, theme, accent, opacity, blur_enabled, highlight, system_light):
    from liquid_glass import dock_theme_colors, dock_tint_layers, material_alpha
    colors = dock_theme_colors(dict(dock_material=material, theme=theme, theme_color=accent,
                                   dock_highlight=highlight), system_light)
    tint, layer_opacity = dock_tint_layers(colors, 100 - opacity)
    alpha = material_alpha(tint, material)
    if not blur_enabled:
        alpha = min(255, alpha + (10 if material == 'crystal' else 20))
    return colors['tint'].name(), (0 if material == 'clear' else round(alpha * layer_opacity)), colors['light']


def appearance(cfg, kind, system_light=True, transparent=True):
    """Resolve without overwriting the user's independent appearance draft."""
    cfg = normalize(dict(cfg))
    prefix = 'shell_' + kind + '_'
    source = cfg[prefix + 'source']
    if source == 'app':
        values = dock_appearance(cfg)
    elif source == 'system':
        values = dict(material='acrylic' if transparent else 'solid', theme='auto',
                      color='#edf3f9' if system_light else '#202830', opacity=72, blur=24, highlight=24)
    else:
        values = {key: cfg[prefix + key] for key in ('material', 'theme', 'color', 'opacity', 'blur', 'highlight')}
    values.setdefault('blur_enabled', True)
    values['text_mode'] = cfg[prefix + 'text_mode']
    values['system_light'] = system_light
    values['light'] = system_light if values['theme'] == 'auto' else values['theme'] == 'light'
    if source == 'app':
        from liquid_glass import material_blur
        values['color'], values['tint_alpha'], values['light'] = _dock_surface(
            values['material'], values['theme'], values['color'], values['opacity'],
            values['blur_enabled'], values['highlight'], system_light)
        values['brush_blur'] = material_blur(values['blur'], values['material'])
    else:
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', str(values['color'])):
            values['color'] = '#deedf9'
        if not values['light']:
            rgb = [round(int(values['color'][i:i+2], 16)*.22) for i in (1, 3, 5)]
            values['color'] = '#' + ''.join(f'{v:02x}' for v in rgb)
    if values['material'] == 'clear':
        values.update(opacity=0, blur_enabled=False)
    elif not transparent:
        values.update(material='solid', opacity=100, blur_enabled=False)
        if source == 'app':
            values['tint_alpha'] = 255
    values['opacity'] = max(0, min(100, values['opacity']))
    return values


def brush_spec(values):
    material, color = values['material'], values['color']
    opacity = max(0, min(100, values['opacity']))
    alpha = values.get('tint_alpha', round(opacity / 100 * 255))
    tint = f'#{alpha:02x}' + color[1:]
    if alpha == 255 or material in ('clear', 'solid', 'mica') or not values['blur_enabled'] or not values['blur']:
        return 'solid', tint, 0
    # Dock composites its tint over the background. Native Acrylic's luminosity
    # blend produces a different colour even when fed the same RGB and opacity.
    if 'tint_alpha' not in values and material in ('acrylic', 'paper_glass'):
        return 'acrylic', tint, opacity
    return 'blur', tint, max(0, min(50, values.get('brush_blur', values['blur'])))


def background(values):
    kind, tint, amount = brush_spec(values)
    if kind == 'solid':
        return f'<SolidColorBrush Color="{tint}"/>'
    if kind == 'acrylic':
        return (f'<AcrylicBrush BackgroundSource="Backdrop" TintColor="#{tint[3:]}" TintOpacity="{amount / 100:.2f}" '
                f'TintLuminosityOpacity="0" FallbackColor="{tint}"/>')
    return f'<WindhawkBlur BlurAmount="{amount}" TintColor="{tint}" FallbackColor="{tint}"/>'


def shows_backdrop(style):
    return style.get('tint_alpha', round(style['opacity'] * 255 / 100)) < 255


def panel_ink(style, surface=None, system_text_light=None):
    mode = style['text_mode']
    if mode == 'white':
        return '#ffffff'
    if mode == 'black':
        return '#000000'
    if mode == 'system':
        light = style['system_light'] if system_text_light is None else system_text_light
        return '#000000' if light else '#ffffff'
    # A sampled surface already includes the brush and backdrop.
    return foreground(surface if surface is not None and shows_backdrop(style) else style['color'])


def menu_color(ink):
    return '#26323e' if ink == '#ffffff' else '#edf5fc'


def panel_highlight(style):
    return round(style['highlight'] * 1.6)


def rules(cfg, kind, system_light=True, transparent=True, surface_color=None, system_text_light=None, layout=None):
    cfg = normalize(dict(cfg))
    style = appearance(cfg, kind, system_light, transparent)
    ink = panel_ink(style, surface_color, system_text_light)
    theme = 'Light' if ink == '#000000' else 'Dark'
    brush = background(style)
    highlight = panel_highlight(style)
    edge = f'#{highlight:02x}ffffff'
    if style['material'] == 'flowing':
        edge_brush = '<LinearGradientBrush StartPoint="0,0" EndPoint="1,1"><GradientStop Color="#b864e8de" Offset="0"/><GradientStop Color="#b88a64eb" Offset="1"/></LinearGradientBrush>'
    else:
        edge_brush = f'<SolidColorBrush Color="{edge}"/>'
    surface = [f'Background:={brush}', 'CornerRadius=18', 'BorderThickness=1', f'BorderBrush:={edge_brush}', f'RequestedTheme={theme}']
    result = []
    def add(target, *properties):
        result.append((target, list(properties)))
    if kind == 'notifications':
        surfaces = [('Grid#NotificationCenterGrid', True),
                    ('Grid#CalendarCenterGrid', cfg['shell_notifications_calendar']),
                    ('Grid#ControlCenterRegion', cfg['shell_notifications_quick']),
                    ('Grid#MediaTransportControlsRegion', cfg['shell_notifications_media']),
                    ('Border#ToastBackgroundBorder, Border#ToastBackgroundBorder2', cfg['shell_notifications_toast'])]
        for target, enabled in surfaces:
            if enabled:
                add(target, *surface)
        if cfg['shell_notifications_calendar']:
            for target in ('ScrollViewer#CalendarControlScrollViewer', 'Border#CalendarHeaderMinimizedOverlay',
                           'Grid#FocusGrid'):
                add(target, 'Background=Transparent', f'RequestedTheme={theme}')
        if cfg['shell_notifications_quick']:
            for target in ('ControlCenter.ControlCenterView#ControlCenterView', 'Grid#ControlCenterRegion > * > Grid#L1Grid'):
                add(target, f'RequestedTheme={theme}')
            add('Grid#L1Grid > Border', 'Background=Transparent')
            button_edge = f'<SolidColorBrush Color="#22{ink[1:]}"/>'
            button_style = ('CornerRadius=30', 'BorderThickness=1', f'BorderBrush:={button_edge}')
            for name in ('ToggleButton', 'SplitL2Button'):
                # CommonStates.Normal also applies when a separate check-state
                # group owns the accent. Leave fill and glyph to the native toggle.
                add(f'ControlCenter.PaginatedToggleButton#{name} > ContentPresenter#ContentPresenter', *button_style)
                add(f'QuickActions.AccessibleToggleButton#{name}', *button_style)
        if cfg['shell_notifications_media']:
            add('Grid#MediaTransportControlsRoot', 'Background=Transparent', f'RequestedTheme={theme}')
            add('Grid#ThumbnailImage > Border', 'CornerRadius=12')
        if cfg['shell_notifications_toast']:
            add('ActionCenter.FlexibleToastView#FlexibleNormalToastView', 'Background=Transparent', f'RequestedTheme={theme}')
    else:
        # One material and edge. Start also has independent shadow borders with
        # square footprints larger than AcrylicBorder on some Windows builds.
        add('Border#AcrylicBorder', *surface)
        add('Border#AcrylicOverlay', 'Background=Transparent', 'BorderThickness=0',
            'BorderBrush=Transparent', 'CornerRadius=18', 'Margin=0', 'Visibility=Collapsed')
        for shadow in START_SHADOWS:
            add(f'Border#{shadow}', 'Visibility=Collapsed')
        layout = layout or start_layout()
        width, height = layout.width, layout.height
        panel_size = ('MinWidth=0', 'MinHeight=0', f'MaxWidth={width}', f'MaxHeight={height}',
                      f'Width={width}', f'Height={height}')
        classic_roots = ('StartDocked.LauncherFrame > Grid#RootGrid',
                         'StartDocked.LauncherFrame > Grid#RootPanel > Grid#RootGrid')
        add('StartDocked.StartSizingFrame', *panel_size, f'RequestedTheme={theme}')
        for root in classic_roots:
            add(root, *panel_size, f'RequestedTheme={theme}')
            add(root + ' > Grid#RootContent', *panel_size, f'RequestedTheme={theme}', 'Background=Transparent', 'CornerRadius=18')
        add('Grid#RootContent > Border#AcrylicBorder', *panel_size, 'Margin=0')
        # The redesigned frame is sized after both native columns are found.
        add('Grid#MainMenu', f'RequestedTheme={theme}', 'Background=Transparent', 'CornerRadius=18')
        # FrameRoot also occurs inside StartInnerFrame. Giving every occurrence
        # the full panel width makes the native pinned column wider than its slot.
        add('Grid#FrameRoot', f'RequestedTheme={theme}', 'Background=Transparent', 'CornerRadius=18')
        for target in ('Grid#AllAppsRoot', 'Grid#UndockedRoot', 'Grid#SideBySidePinnedWrapper'):
            add(target, f'RequestedTheme={theme}')
        # The two generations of Start host the footer in different templates.
        # Draw a single inset rule above the commands, in the current text colour.
        footer = (f'Margin={START_INSET},0,{START_INSET},0', 'Height=48', 'BorderThickness=0,1,0,0',
                  f'BorderBrush:=<SolidColorBrush Color="#20{ink[1:]}"/>')
        add('Grid#NavPanePlaceholder', *footer)
        add('Grid#MainContent > StartDocked.NavigationPaneView#NavigationPane', *footer)
        add('Grid#AllAppsPaneHeader', 'Margin=0', 'Height=36', 'VerticalAlignment=Top')
        add('TextBlock#AllAppsHeading', 'Margin=0,8,0,8', 'HorizontalAlignment=Left')
        for heading in ('AllAppsHeading', 'AllListHeadingText', 'PinnedListHeaderText'):
            add('TextBlock#' + heading, 'FontSize=16', 'FontWeight=SemiBold')
        # The measured viewport adapter owns horizontal margins and widths.
        # A property watcher forcing Margin=0 would undo its compensation.
        add('StartDocked.AppListView', 'Padding=0')
        add('StartDocked.AllAppsGridListView#AppsList', 'Padding=0', 'MinWidth=0',
            'HorizontalContentAlignment=Stretch')
        add('StartDocked.AllAppsGridListViewItem', 'Margin=0', 'Padding=0', 'HorizontalContentAlignment=Stretch')
        add('StartDocked.AllAppsGridListViewItem > Grid#ContentBorder', 'Margin=0', 'Padding=0')
        # BF_AlignStartLetters measures Header.Padding against the first app
        # icon. A watched Padding setter here causes a native XAML layout cycle
        # as soon as a real group and its first app have different origins.
        add('StartDocked.AllAppsGridListViewItem > StackPanel#RootPanel > Button#Header',
            'HorizontalContentAlignment=Left', 'VerticalContentAlignment=Bottom',
            'BorderThickness=0', 'FontSize=12', 'FontWeight=SemiBold')
        add('StartDocked.AllAppsGridListViewItem > StackPanel#RootPanel > Button#Header > Border#Border > TextBlock#Text',
            'Opacity=0.82')
        # Keep the logo, app name and native "new"/download badges in their own columns.
        add('Border#LogoBackgroundPlate', 'Width=24', 'Height=24', 'Margin=8,0,0,0',
            'HorizontalAlignment=Left', 'VerticalAlignment=Center')
        add('Grid#ContentRoot > Rectangle#LogoBorder', 'Width=24', 'Height=24', 'Margin=8,0,0,0',
            'HorizontalAlignment=Left', 'VerticalAlignment=Center')
        app_name = ('FontSize=13', 'TextWrapping=NoWrap', 'TextTrimming=CharacterEllipsis', 'VerticalAlignment=Center')
        add('Grid#ContentRoot > TextBlock#AppDisplayName', 'Margin=12,0,6,0', *app_name)
        add('Grid#ContentRoot > Grid#DownloadIconAndDisplayNameContainer', 'Margin=12,0,6,0')
        add('Grid#DownloadIconAndDisplayNameContainer > TextBlock#AppDisplayName', 'Margin=0', *app_name)
        add('Grid > Grid > TextBlock#AppDisplayName', *app_name)
        add('Grid#AllAppsRoot > * > GridView#AllAppsGrid > * > ItemsWrapGrid > GridViewItem',
            'MinWidth=0', 'Width=Auto', 'Margin=0', 'Padding=0', 'HorizontalAlignment=Stretch', 'HorizontalContentAlignment=Stretch')
        add('StartMenu.PinnedList > Grid#Root', 'Padding=0',
            'ColumnDefinitions:=<ColumnDefinitionCollection><ColumnDefinition Width="*"/><ColumnDefinition Width="10"/></ColumnDefinitionCollection>')
        add('StartMenu.PinnedList > Grid#Root > Microsoft.UI.Xaml.Controls.PipsPager#PinnedListPipsPager',
            'MinWidth=0', 'Width=10', 'Padding=0', 'Margin=0')
        add('GridView#PinnedList', 'Padding=0', 'Margin=0', 'HorizontalAlignment=Stretch')
        add('StartDocked.UserTileView', 'Visibility=Visible', f'RequestedTheme={theme}')
        for control in ('StartDocked.NavigationPaneButton', 'Button'):
            add(control + '#UserTileButton', 'HorizontalAlignment=Left', 'HorizontalContentAlignment=Left',
                'VerticalAlignment=Center', 'VerticalContentAlignment=Center', 'Height=40', 'MinWidth=0',
                f'MaxWidth={max(80, layout.apps_width)}', 'Padding=8,0,12,0', 'BorderThickness=0', 'CornerRadius=8')
        add('Grid#UserTileIcon', 'Width=28', 'Height=28', 'VerticalAlignment=Center')
        add('TextBlock#UserTileNameText', 'Margin=8,0,0,0', 'FontSize=13', 'FontWeight=SemiBold',
            'VerticalAlignment=Center', 'TextWrapping=NoWrap', 'TextTrimming=CharacterEllipsis',
            f'MaxWidth={max(36, layout.apps_width-56)}')
        # Both native lists set local Foreground values; changing their parent
        # theme alone leaves all-apps white and pinned names black.
        for target in ('TextBlock', 'FontIcon', 'SymbolIcon'):
            add(target, f'Foreground={ink}')
        # Cascading Windows menus share the same presenter template at every depth.
        add('MenuFlyoutPresenter', f'Background:={brush}', 'CornerRadius=12', 'BorderThickness=0',
            'BorderBrush=Transparent', f'Foreground={ink}')
        add('FlyoutPresenter', f'Background:={brush}', 'CornerRadius=12', 'BorderThickness=1',
            f'BorderBrush:={edge_brush}', f'Foreground={ink}')
        search = 'Cortana.UI.Views.TaskbarSearchPage'
        search_root = search + ' > Grid#RootGrid'
        search_frame = 'Grid#OuterBorderGrid > Grid#BorderGrid'
        aligned_panel = (*panel_size, 'Margin=0', 'HorizontalAlignment=Left', 'VerticalAlignment=Top')
        add(search, *aligned_panel, f'RequestedTheme={theme}')
        search_chrome = (*aligned_panel, 'Padding=0', 'CornerRadius=18')
        add(search_root, *search_chrome, 'Background=Transparent', f'RequestedTheme={theme}')
        add(search_root + ' > Grid#OuterBorderGrid', *search_chrome)
        add(search_frame, *search_chrome)
        add(search_frame + ' > Border#AppBorder', *surface, *aligned_panel, 'Visibility=Visible')
        for name in ('AccentAppBorder', 'LayerBorder', 'AccentLayerBorder', 'dropshadow'):
            add(search_frame + ' > Border#' + name, 'Visibility=Collapsed')
        input_brush = f'<SolidColorBrush Color="#19{ink[1:]}"/>'
        add('Grid#RootGrid > Border#TaskbarSearchBackground', f'Background:={input_brush}',
            'CornerRadius=12', 'BorderThickness=1', f'BorderBrush:={edge_brush}', f'RequestedTheme={theme}')
        add('Cortana.UI.Views.RichSearchBoxControl#SearchBoxControl > Grid#RootGrid',
            'CornerRadius=12', f'RequestedTheme={theme}')
        add('Cortana.UI.Views.CortanaRichSearchBox#SearchTextBox', f'Foreground={ink}', f'RequestedTheme={theme}')
        add('Grid#WebViewGrid', 'MinWidth=0', 'Background=Transparent', 'CornerRadius=0,0,18,18')
        tile_width, tile_height = layout.cell_width, START_PIN_CELL[1]
        pinned_tiles = (f'MaximumRowsOrColumns={layout.columns}', f'ItemWidth={tile_width}', f'ItemHeight={tile_height}', 'Margin=0')
        add('GridView#PinnedList > Border > ScrollViewer > Border > Grid > ScrollContentPresenter > ItemsPresenter > ItemsWrapGrid', *pinned_tiles)
        folder = 'StartMenu.ExpandedFolderList'
        # A folder is a second reading surface over other labels. Keep its
        # material and hue, with enough backing to separate the two layers.
        folder_style = dict(style, opacity=max(92, style['opacity']))
        if 'tint_alpha' in style:
            folder_style['tint_alpha'] = max(235, style['tint_alpha'])
        if foreground(style['color']) != ink:
            color = blend(style['color'], rgb(menu_color(ink)), .2)
            folder_style['color'] = '#%02x%02x%02x' % tuple(round(channel) for channel in color)
        folder_surface = [f'Background:={background(folder_style)}', *surface[1:]]
        for frame in (folder, 'StartMenu.FolderModal'):
            add(frame, f'RequestedTheme={theme}')
            add(frame + ' > Grid', 'Margin=0', 'MinWidth=0', 'HorizontalAlignment=Stretch')
            add(frame + ' > Grid > Border', *folder_surface, 'Margin=0', 'Width=Auto', 'MinWidth=0',
                'HorizontalAlignment=Stretch')
            add(frame + ' > Grid > Grid', 'Margin=0', 'Padding=0', 'Width=Auto', 'MinWidth=0',
                'HorizontalAlignment=Stretch', 'CornerRadius=12')
        add(folder + ' > Grid',
            'ColumnDefinitions:=<ColumnDefinitionCollection><ColumnDefinition Width="*"/><ColumnDefinition Width="264"/><ColumnDefinition Width="*"/></ColumnDefinitionCollection>',
            'RowDefinitions:=<RowDefinitionCollection><RowDefinition Height="*"/><RowDefinition Height="Auto"/><RowDefinition Height="*"/></RowDefinitionCollection>')
        add(folder + ' > Grid > Grid',
            'Padding=8,4,8,8',
            'ColumnDefinitions:=<ColumnDefinitionCollection><ColumnDefinition Width="*"/><ColumnDefinition Width="20"/></ColumnDefinitionCollection>')
        add('TextBox#ExpandedFolderNameTextBox', 'Margin=10,8,10,8', 'MinWidth=0', 'Width=Auto',
            'FontSize=16', f'Foreground={ink}', f'RequestedTheme={theme}')
        add(folder + ' > Grid > Grid > Microsoft.UI.Xaml.Controls.PipsPager#PinnedListPipsPager', 'Margin=0', 'Padding=0', 'MinWidth=0', 'Width=20')
        container = 'StartMenu.UniversalTileContainer#UniversalTileContainer > Grid#GridViewContainer'
        add(container, 'Width=264', 'Margin=0', 'Padding=8,4,8,8')
        add(container + ' > Grid[2]', 'Margin=0')
        add('TextBox#MutableFolderNameTextBox', 'Margin=8,4,8,4', 'MinWidth=0')
        add('Grid#FolderLabels > TextBlock#FolderNameTextBlock', 'Margin=8,5,8,8')
        folder_tiles = 'GridView#FolderList > Border > ScrollViewer > Border > Grid > ScrollContentPresenter > ItemsPresenter > ItemsWrapGrid'
        folder_lists = ('GridView#FolderList', *(container + ' > Grid > GridView#' + name
                                                for name in ('LevelOneGridView', 'LevelTwoGridView')))
        tile_path = folder_tiles.removeprefix('GridView#FolderList')
        folder_width, folder_height = START_FOLDER_CELL
        for grid in folder_lists:
            add(grid, 'Margin=0', 'Padding=0', 'MinWidth=0', f'Width={folder_width * START_FOLDER_COLUMNS}',
                'HorizontalAlignment=Left', 'ScrollViewer.VerticalScrollMode=Enabled',
                'ScrollViewer.VerticalScrollBarVisibility=Hidden', 'ScrollViewer.HorizontalScrollMode=Disabled',
                'ScrollViewer.HorizontalScrollBarVisibility=Disabled', 'ScrollViewer.BringIntoViewOnFocusChange=True')
            add(grid + tile_path, f'MaximumRowsOrColumns={START_FOLDER_COLUMNS}', 'Orientation=Horizontal',
                f'ItemWidth={folder_width}', f'ItemHeight={folder_height}', 'Margin=0')
        # Resize cell/hover geometry only. Native icon and glyph sizes stay intact.
        for grid, w, h in [('GridView#PinnedList', tile_width, tile_height),
                           *((grid, folder_width, folder_height) for grid in folder_lists)]:
            base = grid + tile_path
            add(base + ' > GridViewItem', 'MinWidth=0', 'MinHeight=0', f'Width={w}', f'Height={h}',
                f'MaxWidth={w}', f'MaxHeight={h}', 'Margin=0', 'Padding=0',
                'HorizontalContentAlignment=Stretch', 'VerticalContentAlignment=Stretch')
            add(base + ' > GridViewItem > Border#ContentBorder', 'MinWidth=0', 'MinHeight=0', 'Margin=0', 'Padding=0')
            # The app and folder data templates both give this inner Grid a
            # fixed PinnedListItemWidth (96 DIPs), independent of the hit tile.
            for presenter in ('Border#ContentBorder > Grid > ContentPresenter#ContentPresenter',
                              'Border#ContentBorder > ContentPresenter', 'ListViewItemPresenter'):
                owner = base + ' > GridViewItem > ' + presenter
                add(owner, 'HorizontalAlignment=Stretch', 'HorizontalContentAlignment=Stretch')
                add(owner + ' > Grid',
                    'Width=Auto', 'MinWidth=0', 'HorizontalAlignment=Stretch')
        add('StartMenu.PinnedListTile, StartMenu.PinnedListTile > Grid#Root',
            'Width=Auto', 'MinWidth=0', 'HorizontalAlignment=Stretch')
        for tile in ('PinnedListTile', 'PinnedListCollapsedFolder'):
            owner = 'StartMenu.' + tile + ' > Grid#Root'
            label_parent = owner + ' > Grid#DisplayNameAndDownloadIconContainer' if tile == 'PinnedListTile' else owner
            add(label_parent + ' > TextBlock#DisplayName', 'Margin=2,4,2,0', 'FontSize=12',
                'MaxLines=2', 'TextWrapping=Wrap', 'TextTrimming=CharacterEllipsis', 'TextAlignment=Center',
                'HorizontalAlignment=Center')
    return result


def search_content_styles(ink, style=None):
    # These selectors target the Windows Search document handled by the bundled engine.
    edge = f'{ink}30'
    menu_background = menu_color(ink)
    menu_styles = ()
    if style is not None:
        # The document is transparent over the shell surface, so the popup
        # can add the current tint and blur without selecting a second theme.
        alpha = style.get('tint_alpha', round(style['opacity'] * 255 / 100))
        menu_background = f'{style["color"]}{alpha:02x}'
        if style['blur_enabled'] and style['blur'] and style['material'] not in ('clear', 'solid', 'mica'):
            menu_styles = (f'backdrop-filter: blur({style["blur"]}px) !important',)
    results = '#root:not(.zeroInput19H1) '
    return (
        ('html, body, #rootContainer, #root, .scr, #searchPane, #qfContainer, .leftPane, .searchResults, .topResults',
         ('background: transparent !important', f'color: {ink} !important')),
        ('#root .groupContainer.curatedSettingsGroup, #root .groupContainer.topItemsGroup, '
         '#root .groupContainer.balloonSuggGroup, [data-region="CuratedSettings"], '
         '[data-region="TopApps"], [data-region^="QuickSearch"], [data-region="QuickWorkSearch"], '
         '[data-region="QuickWorkSearchTopList"], .balloonSuggGroup, '
         '#quickSearches, .quickSearches, .quickSearchGroup, .quickSearchesGroup', ('display: none !important',)),
        ('#root.zeroInput19H1 #qfContainer #groups > div, #root.zeroInput19H1 #groups > .colLayout',
         ('grid-template-columns: minmax(0, 1fr) !important', 'grid-template-rows: auto !important',
          'display: flex !important', 'flex-direction: column !important')),
        ('#root.zeroInput19H1 #groups .colLayoutLeft, #root.zeroInput19H1 #groups .colLayoutRight, '
         '#root.zeroInput19H1 #groups .recommendedSuggGroup, #root.zeroInput19H1 #groups .groupContainer.leftPaneZIsuggestions',
         ('min-width: 0 !important', 'width: 100% !important', 'max-width: 100% !important',
          'box-sizing: border-box !important')),
        (', '.join(results + target for target in ('#qfPreviewPane', '.previewContainer', '.preview-content-container', '.openPreviewPaneBtn')),
         ('display: none !important',)),
        (', '.join(results + target for target in ('.main-content-container', '.search-results-grid', '#searchPane')),
         ('grid-template-columns: minmax(0, 1fr) !important',)),
        (', '.join(results + target for target in ('.suggsListContainer', '#qfSuggsList', '.results-container', '.leftPane', '.left-pane')),
         ('min-width: 0 !important', 'max-width: 100% !important', 'width: 100% !important', 'flex: 1 1 100% !important')),
        ('.groupTitle, .groupHeader, .groupTitleText, .primaryText, .secondaryText, .caption, .subtitle, .cortanaFontIcon, '
         '.suggContainer span, .suggContainer .title, .suggestion span, .suggestion .title',
         (f'color: {ink} !important',)),
        ('#menuContainer, .contextMenu',
         (f'background-color: {menu_background} !important', f'color: {ink} !important',
          'border-radius: 12px !important', f'outline: 1px solid {edge} !important', *menu_styles)),
        ('.contextMenu::before, .contextMenu::after', ('background-color: transparent !important',)),
        ('#menuContainer .menuItem, #menuContainer .menuItem span, .contextMenu .menuItem, .contextMenu .menuItem span',
         (f'color: {ink} !important',)),
        ('.groupHeader, .suggDetailsContainer', ('background-color: transparent !important',)),
        ('.suggContainer, .scope-tile__button',
         ('border-radius: 8px !important', f'color: {ink} !important')),
        ('.suggContainer:hover, .scope-tile__button:hover',
         (f'background-color: {ink}18 !important',)),
        ('.suggContainer:focus-within, .suggContainer[aria-selected="true"], .suggContainer.selected, '
         '.scope-tile__button[aria-selected="true"]',
         (f'background-color: {edge} !important',)),
    )


def settings(cfg, kind, owner_pid, system_light=True, transparent=True, surface_color=None, system_text_light=None, layout=None):
    cfg = normalize(dict(cfg))
    style = appearance(cfg, kind, system_light, transparent)
    ink = panel_ink(style, surface_color, system_text_light)
    data = {'enabled': str(int(cfg[f'shell_{kind}_enabled'])), 'owner_pid': str(owner_pid),
            'theme': 'SideBySideMinimal' if kind == 'start' else '',
            # Never force a legacy OS feature or restart the native shell host.
            'disableNewStartMenuLayout': 'default',
            'bigfish_theme': 'Light' if ink == '#000000' else 'Dark'}
    if kind == 'start' and style['text_mode'] == 'auto' and shows_backdrop(style):
        data['bigfish_live_ink'] = ink
    if kind == 'start':
        layout = layout or _display_start_layout()
    for index, (target, properties) in enumerate(rules(cfg, kind, system_light, transparent, surface_color, system_text_light, layout)):
        data[f'controlStyles[{index}].target'] = target
        for part, value in enumerate(properties):
            data[f'controlStyles[{index}].styles[{part}]'] = value
    if kind == 'start':
        data.update(bigfish_start_width=str(layout.width), bigfish_start_height=str(layout.height),
                    bigfish_pin_columns=str(layout.columns), bigfish_pin_cell_width=str(layout.cell_width),
                    bigfish_pin_cell_height=str(START_PIN_CELL[1]))
        surface = surface_color if surface_color is not None and shows_backdrop(style) else style['color']
        data['bigfish_footer_surface'] = surface if isinstance(surface,str) else '#%02x%02x%02x'%tuple(round(v) for v in surface)
        brush, tint, amount = brush_spec(style)
        data['bigfish_footer_tint'] = tint
        data['bigfish_footer_blur'] = str(amount if brush == 'blur' else style['blur'] if brush == 'acrylic' else 0)
        for index, (target, properties) in enumerate(search_content_styles(ink, style)):
            data[f'webContentStyles[{index}].target'] = target
            for part, value in enumerate(properties):
                data[f'webContentStyles[{index}].styles[{part}]'] = value
    return data


def encode_ini(values):
    # Only this module's generated, bounded keys/values cross the native boundary.
    if any('\n' in str(v) or '\r' in str(v) or '\0' in str(v) for pair in values.items() for v in pair):
        raise ValueError('Invalid shell appearance value')
    text = '[settings]\r\n' + '\r\n'.join(f'{k}={v}' for k, v in values.items()) + '\r\n'
    if len(text) > 60000:
        raise ValueError('Shell appearance settings too large')
    return text.encode('utf-16')
