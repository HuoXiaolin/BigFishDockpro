"""Bounded preferences and native XAML rules for the existing Windows flyouts."""
import re
from appearance_presets import APPEARANCE_SOURCES, dock_appearance
from background_contrast import foreground

KINDS = ('start', 'notifications')
SOURCES = [APPEARANCE_SOURCES[0], ('跟随系统', 'system'), APPEARANCE_SOURCES[1]]
TEXT_MODES = [('自动调整', 'auto'), ('跟随系统', 'system'), ('自定义 · 白色', 'white'), ('自定义 · 黑色', 'black')]
START_STYLES = [('系统默认', False), ('Windows 11 · 玻璃网格', True)]
START_SHADOWS = ('DropShadow', 'StartDropShadow', 'RootGridDropShadow', 'RightCompanionDropShadow')
DEFAULTS = {}
for _kind in KINDS:
    DEFAULTS.update({f'shell_{_kind}_{key}': value for key, value in dict(
        enabled=False, source='app', material='crystal', theme='auto', color='#deedf9',
        opacity=72, blur=24, highlight=38, text_mode='auto').items()})
for _part in ('quick', 'media', 'toast', 'calendar'):
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
    for part, title in (('quick', '快速设置'), ('media', '媒体控制'), ('toast', '通知弹窗'), ('calendar', '日历')):
        fields['shell_notifications_' + part] = (notification_page, title, 'check', None)
    return fields


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
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', str(values['color'])):
        values['color'] = '#deedf9'
    # Preserve the tint in dark mode, while keeping the native foreground legible.
    if not values['light']:
        rgb = [round(int(values['color'][i:i+2], 16)*.22) for i in (1, 3, 5)]
        values['color'] = '#' + ''.join(f'{v:02x}' for v in rgb)
    if values['material'] == 'clear':
        values.update(opacity=0, blur_enabled=False)
    elif not transparent:
        values.update(material='solid', opacity=100, blur_enabled=False)
    values['opacity'] = max(0, min(100, values['opacity']))
    return values


def background(values):
    material, color = values['material'], values['color']
    opacity = max(0, min(100, values['opacity'])) / 100
    tint = f'#{round(opacity*255):02x}' + color[1:]
    if opacity == 1 or material in ('clear', 'solid', 'mica') or not values['blur_enabled'] or not values['blur']:
        return f'<SolidColorBrush Color="{tint}"/>'
    if material in ('acrylic', 'paper_glass'):
        return (f'<AcrylicBrush BackgroundSource="Backdrop" TintColor="{color}" TintOpacity="{opacity:.2f}" '
                f'TintLuminosityOpacity="0" FallbackColor="{tint}"/>')
    return f'<WindhawkBlur BlurAmount="{max(0, min(50, values["blur"]))}" TintColor="{tint}" FallbackColor="{tint}"/>'


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
    return foreground(surface if surface is not None and style['opacity'] < 100 else style['color'])


def rules(cfg, kind, system_light=True, transparent=True, surface_color=None, system_text_light=None):
    cfg = normalize(dict(cfg))
    style = appearance(cfg, kind, system_light, transparent)
    ink = panel_ink(style, surface_color, system_text_light)
    theme = 'Light' if ink == '#000000' else 'Dark'
    brush = background(style)
    highlight = round(style['highlight'] * 1.6)
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
                           'ActionCenter.FocusSessionControl#FocusSessionControl > Grid#FocusGrid'):
                add(target, 'Background=Transparent', f'RequestedTheme={theme}')
        if cfg['shell_notifications_quick']:
            for target in ('ControlCenter.ControlCenterView#ControlCenterView', 'Grid#ControlCenterRegion > * > Grid#L1Grid'):
                add(target, f'RequestedTheme={theme}')
            add('Grid#L1Grid > Border', 'Background=Transparent')
            button_edge = f'<SolidColorBrush Color="#22{ink[1:]}"/>'
            button_style = (f'RequestedTheme={theme}', 'CornerRadius=30', 'BorderThickness=1', f'BorderBrush:={button_edge}')
            # Style the inactive states while Windows continues to indicate active toggles.
            inactive = tuple(f'Background@{state}:=<SolidColorBrush Color="#{alpha}{ink[1:]}"/>'
                             for state, alpha in (('Normal', '18'), ('PointerOver', '28'), ('Pressed', '36')))
            for name in ('ToggleButton', 'SplitL2Button'):
                add(f'ControlCenter.PaginatedToggleButton#{name} > ContentPresenter#ContentPresenter@CommonStates',
                    *button_style, *inactive)
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
        add('Grid#FrameRoot', f'RequestedTheme={theme}', 'MaxHeight=710', 'Background=Transparent', 'CornerRadius=18')
        add('Grid#MainMenu', f'RequestedTheme={theme}', 'Width=640', 'Background=Transparent', 'CornerRadius=18')
        for target in ('Grid#AllAppsRoot', 'Grid#UndockedRoot', 'Grid#SideBySidePinnedWrapper'):
            add(target, f'RequestedTheme={theme}')
        # Both native lists set local Foreground values; changing their parent
        # theme alone leaves all-apps white and pinned names black.
        for target in ('TextBlock', 'FontIcon', 'SymbolIcon'):
            add(target, f'Foreground={ink}')
        # Theme core chooses the correct Windows 11 visual tree.
        add('Grid#SideBySidePinnedWrapper', 'ColumnDefinitions:=<ColumnDefinitionCollection><ColumnDefinition Width="270*"/><ColumnDefinition Width="368*"/></ColumnDefinitionCollection>')
        add('GridView#PinnedList > Border > ScrollViewer > Border > Grid > ScrollContentPresenter > ItemsPresenter > ItemsWrapGrid', 'MaximumRowsOrColumns=3')
    return result


def settings(cfg, kind, owner_pid, system_light=True, transparent=True, surface_color=None, system_text_light=None):
    cfg = normalize(dict(cfg))
    ink = panel_ink(appearance(cfg, kind, system_light, transparent), surface_color, system_text_light)
    data = {'enabled': str(int(cfg[f'shell_{kind}_enabled'])), 'owner_pid': str(owner_pid),
            'theme': 'SideBySideMinimal' if kind == 'start' else '',
            # Never force a legacy OS feature or restart the native shell host.
            'disableNewStartMenuLayout': 'default',
            'bigfish_theme': 'Light' if ink == '#000000' else 'Dark'}
    for index, (target, properties) in enumerate(rules(cfg, kind, system_light, transparent, surface_color, system_text_light)):
        data[f'controlStyles[{index}].target'] = target
        for part, value in enumerate(properties):
            data[f'controlStyles[{index}].styles[{part}]'] = value
    return data


def encode_ini(values):
    # Only this module's generated, bounded keys/values cross the native boundary.
    if any('\n' in str(v) or '\r' in str(v) or '\0' in str(v) for pair in values.items() for v in pair):
        raise ValueError('Invalid shell appearance value')
    text = '[settings]\r\n' + '\r\n'.join(f'{k}={v}' for k, v in values.items()) + '\r\n'
    if len(text) > 60000:
        raise ValueError('Shell appearance settings too large')
    return text.encode('utf-16')
