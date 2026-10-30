"""Wallpaper-only backdrop shared by Dock, collection cards and sticky notes."""
import ctypes
import sys
from ctypes import wintypes
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication


def valid_backdrop(pixmap):
    # Older Windows/drivers can report success yet supply an opaque black mask.
    # Reject only effectively empty frames, never brighten genuine dark images.
    if pixmap is None or pixmap.isNull():return False
    image=pixmap.toImage().scaled(12,12,Qt.IgnoreAspectRatio,Qt.FastTransformation)
    return any(image.pixelColor(x,y).alpha()>8 and max(image.pixelColor(x,y).getRgb()[:3])>3
               for x in range(image.width()) for y in range(image.height()))


def capture_behind(window,windows=()):
    if sys.platform!='win32':return None
    screen=QApplication.screenAt(window.frameGeometry().center()) or QApplication.primaryScreen()
    if screen is None:return None
    try:
        from wallpaper_source import capture
        return capture(window,screen)
    except (OSError,ValueError,AttributeError,RuntimeError):return None


def surface_windows(dock):
    runtime=getattr(getattr(dock,'tray',None),'runtime',None)
    clock=getattr(runtime,'clock',None);calendar=getattr(runtime,'calendar',None)
    windows=[dock]+([clock] if clock else [])+([calendar] if calendar else [])+[window for manager in (getattr(runtime,'panels',None),getattr(runtime,'notes',None))
                   for window in getattr(manager,'windows',{}).values()]

    return windows


def smooth_backdrop(pixmap,radius):
    """One-shot native-pixel blur, without shrinking wallpaper into a coarse grid.

    The scene/effect and padded working image are released before returning. No
    graphics effect is attached to a live window or run by the paint callback.
    """
    import math
    from PyQt5.QtCore import QRectF
    from PyQt5.QtGui import QPixmap,QPainter
    from PyQt5.QtWidgets import QGraphicsScene,QGraphicsBlurEffect
    if pixmap is None or pixmap.isNull():return pixmap
    ratio=float(pixmap.devicePixelRatio()) or 1.0
    amount=max(0,float(radius))*ratio
    if amount<.1:return pixmap
    width,height=pixmap.width(),pixmap.height();pad=max(2,math.ceil(amount*2))
    source=QPixmap(pixmap);source.setDevicePixelRatio(1)
    padded=QPixmap(width+pad*2,height+pad*2);padded.fill(Qt.transparent)
    painter=QPainter(padded)
    # Clamp edge pixels so blurring never introduces a transparent/black fringe.
    pieces=[(pad,pad,width,height,0,0,width,height),
            (0,pad,pad,height,0,0,1,height),(pad+width,pad,pad,height,width-1,0,1,height),
            (pad,0,width,pad,0,0,width,1),(pad,pad+height,width,pad,0,height-1,width,1),
            (0,0,pad,pad,0,0,1,1),(pad+width,0,pad,pad,width-1,0,1,1),
            (0,pad+height,pad,pad,0,height-1,1,1),(pad+width,pad+height,pad,pad,width-1,height-1,1,1)]
    for x,y,w,h,sx,sy,sw,sh in pieces:painter.drawPixmap(QRectF(x,y,w,h),source,QRectF(sx,sy,sw,sh))
    painter.end()
    result=QPixmap(width,height);result.fill(Qt.transparent)
    scene=QGraphicsScene();scene.setSceneRect(0,0,padded.width(),padded.height());item=scene.addPixmap(padded)
    effect=QGraphicsBlurEffect();effect.setBlurHints(QGraphicsBlurEffect.QualityHint);effect.setBlurRadius(amount);item.setGraphicsEffect(effect)
    painter=QPainter(result);painter.setRenderHint(QPainter.Antialiasing);painter.setRenderHint(QPainter.SmoothPixmapTransform)
    try:scene.render(painter,QRectF(0,0,width,height),QRectF(pad,pad,width,height),Qt.IgnoreAspectRatio)
    finally:painter.end();scene.clear()
    result.setDevicePixelRatio(ratio)
    return result
