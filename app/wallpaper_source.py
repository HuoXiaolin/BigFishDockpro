"""Render Windows wallpaper pixels, without capturing any application window."""
import ctypes,os,time
from ctypes import wintypes
from functools import lru_cache
from PyQt5.QtCore import Qt,QRect,QRectF,QSize
from PyQt5.QtGui import QImage,QImageReader,QPainter,QColor,QPixmap

_metadata={}


def desktop_wallpaper(window):
    from native_file_menu import GUID,method,release
    ole=ctypes.WinDLL('ole32');ole.CoInitializeEx.argtypes=[ctypes.c_void_p,wintypes.DWORD];ole.CoInitializeEx.restype=ctypes.c_long
    initialized=ole.CoInitializeEx(None,2)>=0;pointer=ctypes.c_void_p()
    ole.CoTaskMemFree.argtypes=[ctypes.c_void_p];ole.CoCreateInstance.argtypes=[ctypes.POINTER(GUID),ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(GUID),ctypes.POINTER(ctypes.c_void_p)];ole.CoCreateInstance.restype=ctypes.c_long
    try:
        clsid=GUID('C2CF3110-460E-4FC1-B9D0-8A1C0C9CC4BD');iid=GUID('B92B56A9-8B55-4E14-9A89-0199BBB6F93B')
        if ole.CoCreateInstance(ctypes.byref(clsid),None,23,ctypes.byref(iid),ctypes.byref(pointer))<0:raise OSError('Wallpaper service unavailable')
        count=wintypes.UINT();position=ctypes.c_int(4);color=wintypes.DWORD()
        method(pointer,6,ctypes.c_long,ctypes.POINTER(wintypes.UINT))(pointer,ctypes.byref(count))
        method(pointer,11,ctypes.c_long,ctypes.POINTER(ctypes.c_int))(pointer,ctypes.byref(position));method(pointer,9,ctypes.c_long,ctypes.POINTER(wintypes.DWORD))(pointer,ctypes.byref(color))
        user=ctypes.windll.user32;user.MonitorFromWindow.argtypes=[wintypes.HWND,wintypes.DWORD];user.MonitorFromWindow.restype=wintypes.HANDLE
        class Info(ctypes.Structure):_fields_=[('size',wintypes.DWORD),('monitor',wintypes.RECT),('work',wintypes.RECT),('flags',wintypes.DWORD)]
        info=Info();info.size=ctypes.sizeof(info);user.GetMonitorInfoW.argtypes=[wintypes.HANDLE,ctypes.POINTER(Info)];user.GetMonitorInfoW(user.MonitorFromWindow(int(window.winId()),2),ctypes.byref(info))
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
    finally:
        release(pointer)
        if initialized:ole.CoUninitialize()


@lru_cache(maxsize=2)
def image_file(path,stamp):
    reader=QImageReader(path);reader.setAutoTransform(True);size=reader.size()
    if max(size.width(),size.height())>1024:reader.setScaledSize(size.scaled(QSize(1024,1024),Qt.KeepAspectRatio))
    image=reader.read();image.setText('source_width',str(size.width()));image.setText('source_height',str(size.height()));return image


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


def capture(window,screen):
    key=screen.name();now=time.monotonic();cached=_metadata.get(key)
    if cached is None or now-cached[0]>=2:
        cached=(now,desktop_wallpaper(window));_metadata[key]=cached
    path,position,color,monitor,bounds=cached[1]
    try:source=image_file(path,os.stat(path).st_mtime_ns) if path else QImage()
    except OSError:source=QImage()
    # A missing file falls back to the configured desktop color, never a screenshot.
    logical=screen.geometry();rect=window.frameGeometry();sx=monitor.width()/logical.width();sy=monitor.height()/logical.height()
    region=QRectF(monitor.left()+(rect.left()-logical.left())*sx,monitor.top()+(rect.top()-logical.top())*sy,rect.width()*sx,rect.height()*sy)
    ratio=window.devicePixelRatioF();pixels=QSize(max(1,round(rect.width()*ratio)),max(1,round(rect.height()*ratio)))
    result=QPixmap.fromImage(render(source,position,color,monitor,bounds,region,pixels));result.setDevicePixelRatio(ratio);return result
