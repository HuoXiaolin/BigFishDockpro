"""Local foregrounds and translucent variants of the original capsule badge hues."""
from functools import lru_cache

from PyQt5.QtGui import QColor

from background_contrast import blend, contrast
from clock_legibility import readable
from resource_options import DEFAULT_BADGE_STRENGTH


@lru_cache(maxsize=1024)
def _legible(accent, background, light):
    return readable(accent,[QColor(*background)],polarity=not light).name()


def area_colors(window, rect, colors):
    state=getattr(window,'_content_contrast',None)
    background=state.background_at(rect) if state is not None else None
    if background is None:return colors
    light=contrast(background,'#000000')>=contrast(background,'#ffffff')
    return dict(colors,light=light,background_rgb=background,
                ink=_legible('#101b25' if light else '#ffffff',background,light),
                muted=_legible('#34485a' if light else '#e1ebf3',background,light),
                hover='#e4ebf0' if light else '#39414a')


def text_ink(accent,colors):
    background=colors.get('background_rgb')
    return _legible(QColor(accent).name(),background,colors['light']) if background is not None else accent


def content_colors(window,rect,colors):
    if getattr(window,'_content_contrast',None) is None:return colors
    from capsule_scale import window_rect
    return area_colors(window,window_rect(window,rect),colors)


def widget_colors(owner,child,rect=None):
    from capsule_scale import widget_rect
    area=widget_rect(owner,child,child.rect() if rect is None else rect)
    return area_colors(owner,area,owner.colors)


@lru_cache(maxsize=256)
def _wash(accent,light,active,strength):
    hue,saturation,_,_=QColor(accent).getHslF()
    # Preserve the original function hue in both modes. Off states keep a quieter tint.
    saturation *= 1 if active else .64
    tint=QColor.fromHslF(hue,saturation,.66 if light else .34)
    peak=(205 if light else 235) if active else (131 if light else 150)
    tint.setAlpha(round(peak*strength/100))
    return tint.rgba()


def badge_fill(accent,colors,active=True):
    return QColor.fromRgba(_wash(QColor(accent).name(),colors['light'],active,colors.get('badge_strength',DEFAULT_BADGE_STRENGTH)))


def on_badge(colors,fill):
    background=colors.get('background_rgb')
    if background is None:return colors
    rgb=tuple(round(v) for v in blend(fill.getRgb()[:3],background,fill.alphaF()))
    light=contrast(rgb,'#000000')>=contrast(rgb,'#ffffff')
    return dict(colors,light=light,background_rgb=rgb,ink=_legible(colors['ink'],rgb,light),
                muted=_legible(colors['muted'],rgb,light))
