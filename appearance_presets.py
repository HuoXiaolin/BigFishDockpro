"""Appearance-only presets. Geometry, data and interaction remain independent."""
MATERIALS = [('液态玻璃','liquid'), ('高光玻璃','gloss'), ('亚克力','acrylic'), ('云母','mica'), ('通透','clear'), ('纯色','solid')]
COLOR_MODES = [('跟随系统','auto'), ('浅色','light'), ('深色','dark')]
PANEL_PRESETS = [
    ('轻透液态', dict(opacity=38, blur=6, highlight=45, material='liquid', theme='light', color='#b8d9ef')),
    ('柔雾玻璃', dict(opacity=64, blur=16, highlight=35, material='acrylic', theme='light', color='#ced9e5')),
    ('高光玻璃', dict(opacity=45, blur=8, highlight=75, material='gloss', theme='light', color='#b7ddeb')),
    ('沉静云母', dict(opacity=86, blur=12, highlight=25, material='mica', theme='dark', color='#71869b')),
    ('全透明', dict(opacity=0, blur=2, highlight=0, material='clear', theme='auto', color='')),
]
DOCK_PRESETS = [
    ('轻透液态', dict(theme='light', transparency=68, blur_px=6, dock_highlight=45, theme_color='#b8d9ef', glass=True, clear_background=False)),
    ('柔雾玻璃', dict(theme='light', transparency=38, blur_px=16, dock_highlight=35, theme_color='#ced9e5', glass=True, clear_background=False)),
    ('高光玻璃', dict(theme='light', transparency=55, blur_px=8, dock_highlight=75, theme_color='#b7ddeb', glass=True, clear_background=False)),
    ('沉静深色', dict(theme='dark', transparency=32, blur_px=12, dock_highlight=25, theme_color='#71869b', glass=True, clear_background=False)),
    ('全透明', dict(theme='auto', transparency=100, blur_px=3, dock_highlight=0, theme_color='', glass=False, clear_background=True)),
]
for (_, values), material in zip(DOCK_PRESETS, ['liquid','acrylic','gloss','mica','clear']):
    values['dock_material'] = material
