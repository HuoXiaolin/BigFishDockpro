"""Choose a readable foreground against a solid or composited background."""
from functools import lru_cache


def rgb(color):
    return tuple(int(color[i:i+2], 16) for i in (1, 3, 5))


def _luminance(value):
    linear = [v/255/12.92 if v/255 <= .04045 else ((v/255+.055)/1.055)**2.4 for v in value]
    return sum(v*w for v, w in zip(linear, (.2126, .7152, .0722)))


def blend(color, backdrop, opacity):
    value = rgb(color) if isinstance(color, str) else color
    if backdrop is None:
        return value
    opacity = max(0, min(1, opacity))
    return tuple(a*opacity+b*(1-opacity) for a, b in zip(value, backdrop))


def foreground(color, backdrop=None, opacity=1):
    luminance = _luminance(blend(color, backdrop, opacity))
    return '#000000' if (luminance+.05)/.05 >= 1.05/(luminance+.05) else '#ffffff'


def contrast(color, ink):
    light, dark = sorted((_luminance(color), _luminance(rgb(ink))), reverse=True)
    return (light + .05) / (dark + .05)


def majority_surface(colors):
    """Keep a real sample whose luminance represents the majority of the surface."""
    ordered = sorted(colors, key=_luminance)
    return ordered[len(ordered)//2] if ordered else None


@lru_cache(maxsize=32)
def _pixels(key, rect):
    from PyQt5.QtCore import QRect, QRectF, QSize
    from PyQt5.QtGui import QColor, QImage
    from wallpaper_source import image_file, render
    path, stamp, position, color, monitor, bounds = key
    source = image_file(path, stamp) if path and stamp is not None else QImage()
    sample = render(source, position, QColor.fromRgba(color), QRect(*monitor), QRect(*bounds), QRectF(*rect), QSize(16, 16))
    return tuple(sample.pixelColor(x,y).getRgb()[:3] for y in range(16) for x in range(16))


def wallpaper_samples(window, local_rect=None, *, allow_fallback=False):
    """Read wallpaper files only; never capture foreground applications."""
    from PyQt5.QtCore import QPoint, QRectF
    from PyQt5.QtGui import QGuiApplication
    from wallpaper_source import wallpaper_key, image_file
    screen = window.screen()
    if screen is None:return None
    if local_rect is None:
        from resource_taskbar import taskbars
        bars = taskbars(include_hidden=True)
        if not bars:return None
        bar = next((item for item in bars if item['screen'] == screen.name()), bars[0])
        if bar['screen'] != screen.name():
            screen = next((item for item in QGuiApplication.screens() if item.name() == bar['screen']), None)
            if screen is None:return None
        key = wallpaper_key(bar['hwnd'], screen)
        path, stamp = key[:2]
        if path and (stamp is None or image_file(path, stamp).isNull()):return None
        logical = screen.geometry()
        rect = bar['rect']
        # A fixed strip at this edge stays in place when Explorer auto-hides the bar.
        if rect.width() >= rect.height():
            height = min(32, logical.height())
            top = logical.top() if rect.center().y() < logical.center().y() else logical.bottom() + 1 - height
            area = QRectF(logical.left(), top, logical.width(), height)
        else:
            width = min(32, logical.width())
            left = logical.left() if rect.center().x() < logical.center().x() else logical.right() + 1 - width
            area = QRectF(left, logical.top(), width, logical.height())
    else:
        if local_rect.isEmpty():return None
        key = wallpaper_key(window, screen, allow_fallback=True) if allow_fallback else wallpaper_key(window, screen)
        path, stamp = key[:2]
        if path and (stamp is None or image_file(path, stamp).isNull()):return None
        logical = screen.geometry()
        area = QRectF(local_rect).translated(window.mapToGlobal(QPoint(0,0)))
    monitor = QRectF(*key[4])
    sx, sy = monitor.width()/max(1, logical.width()), monitor.height()/max(1, logical.height())
    region = QRectF(monitor.x() + (area.x() - logical.x())*sx, monitor.y() + (area.y() - logical.y())*sy,
                    area.width()*sx, area.height()*sy)
    return _pixels(key, region.getRect())


def wallpaper_color(window, local_rect=None):
    samples = wallpaper_samples(window, local_rect)
    if samples:
        return tuple(sum(channel)/len(samples) for channel in zip(*samples))
