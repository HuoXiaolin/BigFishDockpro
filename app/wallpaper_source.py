"""Render Windows wallpaper pixels, without capturing any application window."""
import ctypes,os,time,math
from contextlib import contextmanager
from ctypes import wintypes
from functools import lru_cache
from PyQt5.QtCore import Qt,QRect,QRectF,QSize
from PyQt5.QtGui import QImage,QImageReader,QPainter,QColor,QPixmap

_metadata={}
MAX_WALLPAPER_PIXELS=256*1024  # Shared blurred texture, at most 1 MiB; retain original screen coordinates.


class WallpaperServiceError(OSError):
    def __init__(self,hresult):
        self.hresult=hresult & 0xffffffff
        super().__init__(f'Wallpaper service unavailable (HRESULT 0x{self.hresult:08X})')


@contextmanager
def wallpaper_service():
    from native_file_menu import GUID,release
    ole=ctypes.WinDLL('ole32');ole.CoInitializeEx.argtypes=[ctypes.c_void_p,wintypes.DWORD];ole.CoInitializeEx.restype=ctypes.c_long
    initialized=ole.CoInitializeEx(None,2)>=0;pointer=ctypes.c_void_p()
    ole.CoTaskMemFree.argtypes=[ctypes.c_void_p];ole.CoCreateInstance.argtypes=[ctypes.POINTER(GUID),ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(GUID),ctypes.POINTER(ctypes.c_void_p)];ole.CoCreateInstance.restype=ctypes.c_long
    try:
        clsid=GUID('C2CF3110-460E-4FC1-B9D0-8A1C0C9CC4BD');iid=GUID('B92B56A9-8B55-4E14-9A89-0199BBB6F93B')
        result=ole.CoCreateInstance(ctypes.byref(clsid),None,23,ctypes.byref(iid),ctypes.byref(pointer))
        if result<0:raise WallpaperServiceError(result)
        yield pointer,ole
    finally:
        release(pointer)
        if initialized:ole.CoUninitialize()


def set_wallpaper(path):
    from native_file_menu import method
    with wallpaper_service() as (pointer,_):
        setter=method(pointer,3,ctypes.c_long,wintypes.LPCWSTR,wintypes.LPCWSTR)
        if setter(pointer,None,os.path.abspath(path))<0:raise OSError('Windows could not set the wallpaper')


class MonitorInfo(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('monitor', wintypes.RECT),
                ('work', wintypes.RECT), ('flags', wintypes.DWORD)]


def _window_monitor(window):
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user.MonitorFromWindow.restype = wintypes.HANDLE
    user.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
    hwnd = window if isinstance(window, int) else int(window.winId())
    info = MonitorInfo()
    info.size = ctypes.sizeof(info)
    if not user.GetMonitorInfoW(user.MonitorFromWindow(hwnd, 2), ctypes.byref(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    return info


def system_wallpaper(window):
    """Read the primary desktop image when per-monitor wallpaper metadata is unavailable."""
    import winreg
    info = _window_monitor(window)
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
    path = ctypes.create_unicode_buffer(32768)
    if not user.SystemParametersInfoW(0x0073, len(path), path, 0):  # SPI_GETDESKWALLPAPER
        raise ctypes.WinError(ctypes.get_last_error())
    position = 4
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Control Panel\Desktop') as key:
            style = winreg.QueryValueEx(key, 'WallpaperStyle')[0]
            position = {'0': 0, '2': 2, '6': 3, '10': 4, '22': 5}.get(str(style), 4)
            if str(winreg.QueryValueEx(key, 'TileWallpaper')[0]) == '1':
                position = 1
    except OSError:
        pass
    if position != 5 and not (info.flags & 1):
        # SPI only identifies the primary image; a secondary monitor may have its own.
        raise OSError('Per-monitor wallpaper is unavailable')
    rect = info.monitor
    monitor = QRect(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
    bounds = QRect(*(user.GetSystemMetrics(i) for i in (76, 77, 78, 79)))
    value = user.GetSysColor(1)  # COLOR_DESKTOP
    return path.value, position, QColor(value & 255, (value >> 8) & 255, (value >> 16) & 255), monitor, bounds


def desktop_wallpaper(window):
    from native_file_menu import method
    with wallpaper_service() as (pointer,ole):
        count=wintypes.UINT();position=ctypes.c_int(4);color=wintypes.DWORD()
        method(pointer,6,ctypes.c_long,ctypes.POINTER(wintypes.UINT))(pointer,ctypes.byref(count))
        method(pointer,11,ctypes.c_long,ctypes.POINTER(ctypes.c_int))(pointer,ctypes.byref(position));method(pointer,9,ctypes.c_long,ctypes.POINTER(wintypes.DWORD))(pointer,ctypes.byref(color))
        info = _window_monitor(window)
        selected=None;bounds=QRect()
        for index in range(min(count.value,32)):
            name=ctypes.c_void_p();path=ctypes.c_void_p();rect=wintypes.RECT()
            try:
                if method(pointer,5,ctypes.c_long,wintypes.UINT,ctypes.POINTER(ctypes.c_void_p))(pointer,index,ctypes.byref(name))<0:continue
                monitor_id=ctypes.wstring_at(name)
                if method(pointer,7,ctypes.c_long,wintypes.LPCWSTR,ctypes.POINTER(wintypes.RECT))(pointer,monitor_id,ctypes.byref(rect))<0:continue
                area=QRect(rect.left,rect.top,rect.right-rect.left,rect.bottom-rect.top)
                if area.isEmpty():continue
                bounds=bounds.united(area)
                if (rect.left,rect.top,rect.right,rect.bottom)==(info.monitor.left,info.monitor.top,info.monitor.right,info.monitor.bottom):
                    if method(pointer,4,ctypes.c_long,wintypes.LPCWSTR,ctypes.POINTER(ctypes.c_void_p))(pointer,monitor_id,ctypes.byref(path))<0:raise OSError('Wallpaper path unavailable')
                    selected=(ctypes.wstring_at(path) if path else '',area)
            finally:
                if name:ole.CoTaskMemFree(name)
                if path:ole.CoTaskMemFree(path)
        if selected is None:raise OSError('No matching wallpaper monitor')
        return selected[0],position.value,QColor(color.value&255,(color.value>>8)&255,(color.value>>16)&255),selected[1],bounds


@lru_cache(maxsize=1)
def image_file(path,stamp):
    reader=QImageReader(path);reader.setAutoTransform(True);size=reader.size()
    pixels=size.width()*size.height()
    if pixels>MAX_WALLPAPER_PIXELS:
        factor=math.sqrt(MAX_WALLPAPER_PIXELS/pixels)
        reader.setScaledSize(QSize(max(1,int(size.width()*factor)),max(1,int(size.height()*factor))))
    image=reader.read()
    if image.depth()>32:image=image.convertToFormat(QImage.Format_ARGB32_Premultiplied)
    image.setText('source_width',str(size.width()));image.setText('source_height',str(size.height()));return image


def render(image,position,color,monitor,bounds,region,size):
    result=QImage(size,QImage.Format_ARGB32_Premultiplied);result.fill(color)
    if image.isNull():return result
    target=QRectF(bounds if position==5 else monitor);painter=QPainter(result);painter.setRenderHint(QPainter.SmoothPixmapTransform)
    painter.scale(size.width()/region.width(),size.height()/region.height());painter.translate(-region.left(),-region.top())
    if position==1:
        # A bounded sample tile, repeated in native screen coordinates.
        tile=QPixmap.fromImage(image);tile.setDevicePixelRatio(image.width()/max(1,int(image.text('source_width') or image.width())));painter.drawTiledPixmap(region,tile,region.topLeft()-target.topLeft())
    else:
        if position in (0,2,3,4,5):
            if position==2:dest=target
            else:
                factor=max(1,int(image.text('source_width') or image.width()))/image.width() if position==0 else min(target.width()/image.width(),target.height()/image.height()) if position==3 else max(target.width()/image.width(),target.height()/image.height())
                width=image.width()*factor;height=image.height()*factor;dest=QRectF(target.center().x()-width/2,target.center().y()-height/2,width,height)
            painter.setClipRect(target);painter.drawImage(dest,image)
    painter.end();return result


def invalidate_source():
    _metadata.clear()
    image_file.cache_clear()


def _readable_image(path):
    try:
        return bool(path) and not image_file(path,os.stat(path).st_mtime_ns).isNull()
    except OSError:
        return False


def _source_for_monitor(window,allow_fallback):
    try:
        info=desktop_wallpaper(window)
    except OSError:
        if not allow_fallback:raise
        info=system_wallpaper(window)
        used_system=True
    else:
        used_system=False
    if not allow_fallback or not info[0] or _readable_image(info[0]):
        return info
    if not used_system:
        try:
            alternate=system_wallpaper(window)
            if alternate[0]!=info[0] and _readable_image(alternate[0]):
                return alternate
        except OSError:
            pass
    # Only the primary desktop and a spanned image can use this shared Windows cache.
    appdata=os.environ.get('APPDATA')
    if appdata and (info[1]==5 or _window_monitor(window).flags & 1):
        cache=os.path.join(appdata,'Microsoft','Windows','Themes','TranscodedWallpaper')
        if _readable_image(cache):
            return (cache,*info[1:])
    return info


def source_info(window,screen,allow_fallback=False):
    key=screen.name(),allow_fallback;now=time.monotonic();cached=_metadata.get(key)
    if cached is None or now-cached[0]>=2:
        info=_source_for_monitor(window,allow_fallback)
        cached=(now,info);_metadata[key]=cached
        # Screen names can change after docking. Metadata must stay bounded.
        if len(_metadata)>16:
            for old in sorted(_metadata,key=lambda name:_metadata[name][0])[:-16]:_metadata.pop(old,None)
    return cached[1]


def wallpaper_key(window,screen,*,allow_fallback=False):
    path,position,color,monitor,bounds=source_info(window,screen,allow_fallback)
    try:
        stamp=os.stat(path).st_mtime_ns if path else None
    except OSError:
        stamp=None
    return path,stamp,position,color.rgba(),monitor.getRect(),bounds.getRect()


def capture(window,screen,*,allow_fallback=False):
    info=source_info(window,screen,allow_fallback)
    path,position,color,monitor,bounds=info
    try:source=image_file(path,os.stat(path).st_mtime_ns) if path else QImage()
    except OSError:source=QImage()
    # A missing file falls back to the configured desktop color, never a screenshot.
    logical=screen.geometry();rect=window.frameGeometry();sx=monitor.width()/logical.width();sy=monitor.height()/logical.height()
    region=QRectF(monitor.left()+(rect.left()-logical.left())*sx,monitor.top()+(rect.top()-logical.top())*sy,rect.width()*sx,rect.height()*sy)
    ratio=window.devicePixelRatioF();pixels=QSize(max(1,round(rect.width()*ratio)),max(1,round(rect.height()*ratio)))
    result=QPixmap.fromImage(render(source,position,color,monitor,bounds,region,pixels));result.setDevicePixelRatio(ratio);return result
