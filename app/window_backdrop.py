"""Resolve backdrop mode independently of the saved appearance preference."""

BACKDROP_HINT = '置顶时可选择动态透明。置底时使用所在屏幕的壁纸，模糊强度用于壁纸。'


def component_backdrop(cfg, component, *, custom_top=None):
    from window_layers import effective_top
    if custom_top is None:
        custom_top = cfg.get(component + '_layer', 'top') == 'top'
    if effective_top(cfg, custom_top):
        return cfg.get(component + '_backdrop_mode', 'dynamic')
    return 'wallpaper'


def desktop_backdrop(widget, cfg):
    """Resolve the host of an embedded page and the layer of a detached card."""
    from capsule_scale import native_host
    host = native_host(widget)
    key = host.property('clickThroughKey') or host.property('desktopLayerKey') or ''
    component, _, identity = key.partition(':')
    if component == 'resource' and identity:
        return component_backdrop(cfg, 'resource', custom_top=False)
    if component == 'resource' and getattr(host,'taskbar_placement',None) and host.taskbar_slot() is not None:
        return 'wallpaper'
    if component in ('panel', 'resource', 'flash', 'spectrum', 'watermark'):
        return component_backdrop(cfg, component)
    if component == 'note':
        return component_backdrop(cfg, component, custom_top=host.row()['pinned'])
    if component in ('picture', 'custom', 'clock', 'calendar'):
        return component_backdrop(cfg, component, custom_top=False)
    return 'wallpaper'


def uses_wallpaper(mode, appearance):
    return mode == 'wallpaper' and appearance['material'] not in ('clear', 'solid')
