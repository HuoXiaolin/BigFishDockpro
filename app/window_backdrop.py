"""Resolve backdrop mode independently of the saved appearance preference."""

BACKDROP_HINT = '置顶时可选择动态透明。置底时使用所在屏幕的壁纸，模糊强度用于壁纸。'


def component_backdrop(cfg, component):
    # The flash windows are always topmost and have no desktop layer setting.
    if cfg.get(component + '_layer', 'top') == 'top':
        return cfg[component + '_backdrop_mode']
    return 'wallpaper'


def uses_wallpaper(mode, appearance):
    return mode == 'wallpaper' and appearance['material'] not in ('clear', 'solid')
