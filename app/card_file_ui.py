"""Shell-composed state icons and bounded file-name layout for collection cards."""
import ctypes
import os
from ctypes import wintypes
from PyQt5.QtCore import Qt, QRect, QSize
from PyQt5.QtGui import QIcon, QPalette, QTextLayout, QTextOption, QFontMetrics
from PyQt5.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle, QApplication, QListView


def card_display_name(row,hide_extension=False):
    name=row['name']
    if not hide_extension or os.path.isdir(row['path']):return name
    suffix=os.path.splitext(row['path'])[1]
    return name[:-len(suffix)] if suffix and name.lower().endswith(suffix.lower()) else name


def card_overlay_index(overlay,shortcut_overlay,hide_shortcut):
    return 0 if hide_shortcut and shortcut_overlay>0 and overlay==shortcut_overlay else overlay


def extract_card_hicon(api,path,pixels,hide_shortcut=False):
    # Ask the real item, never USEFILEATTRIBUTES: registered overlay handlers
    # (encryption, shortcuts, sync) need the actual path and current Shell state.
    api.user32.DestroyIcon.argtypes=[wintypes.HICON]
    shell=ctypes.WinDLL('shell32',use_last_error=True)
    shell.SHGetFileInfoW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,ctypes.POINTER(api.SHFILEINFOW),wintypes.UINT,wintypes.UINT]
    shell.SHGetFileInfoW.restype=ctypes.c_size_t
    info=api.SHFILEINFOW()
    if not shell.SHGetFileInfoW(path,0,ctypes.byref(info),ctypes.sizeof(info),0x100|0x4000|0x20|0x40):return None
    fallback=info.hIcon
    overlay=(info.iIcon>>24)&0xff
    if hide_shortcut and overlay:
        shell.SHGetIconOverlayIndexW.argtypes=[wintypes.LPCWSTR,ctypes.c_int]
        shell.SHGetIconOverlayIndexW.restype=ctypes.c_int
        # IDO_SHGIOI_LINK is the documented standard shortcut overlay slot.
        shortcut=shell.SHGetIconOverlayIndexW(None,0x0ffffffe)
        filtered=card_overlay_index(overlay,shortcut,True)
        if filtered!=overlay:
            base=api.SHFILEINFOW()
            if shell.SHGetFileInfoW(path,0,ctypes.byref(base),ctypes.sizeof(base),0x100|0x4000):
                if fallback:api.user32.DestroyIcon(fallback)
                fallback=base.hIcon
            overlay=filtered
    try:
        if api._SHGetImageList:
            from native_file_menu import method,release
            index=info.iIcon&0xffffff
            for size in ((1,0) if pixels<=24 else (2,0)):
                image_list=ctypes.c_void_p()
                if api._SHGetImageList(size,ctypes.byref(api._IID_IIMAGELIST),ctypes.byref(image_list))!=0 or not image_list:continue
                try:
                    icon=wintypes.HICON()
                    result=method(image_list,10,ctypes.c_long,ctypes.c_int,ctypes.c_uint,ctypes.POINTER(wintypes.HICON))(image_list,index,1|(overlay<<8),ctypes.byref(icon))
                    if result>=0 and icon.value:
                        if fallback:api.user32.DestroyIcon(fallback)
                        fallback=None
                        return icon.value
                finally:release(image_list)
        icon=fallback;fallback=None;return icon
    finally:
        if fallback:api.user32.DestroyIcon(fallback)


def file_name_lines(text,font,width):
    layout=QTextLayout(text,font);option=QTextOption();option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere);layout.setTextOption(option)
    layout.beginLayout();lines=[]
    for _ in range(3):
        line=layout.createLine()
        if not line.isValid():break
        line.setLineWidth(max(1,width));start=line.textStart();length=line.textLength()
        remaining=text[start:]
        lines.append(QFontMetrics(font).elidedText(remaining,Qt.ElideRight,width) if len(lines)==2 and start+length<len(text) else text[start:start+length].rstrip())
    layout.endLayout();return lines


class FileNameDelegate(QStyledItemDelegate):
    def paint(self,painter,option,index):
        opt=QStyleOptionViewItem(option);self.initStyleOption(opt,index)
        view=opt.widget;is_list=view.viewMode()==QListView.ListMode
        text=opt.text;icon=QIcon(opt.icon);opt.text='';opt.icon=QIcon()
        # Only the selection/hover surface is native; names and icons are drawn below.
        # An empty native label still gets a focus mark over our custom filename.
        opt.state &= ~QStyle.State_HasFocus
        opt.features &= ~(QStyleOptionViewItem.HasDisplay|QStyleOptionViewItem.HasDecoration)
        style=view.style() if view else QApplication.style()
        painter.save();painter.setClipRect(opt.rect);style.drawControl(QStyle.CE_ItemViewItem,opt,painter,view)
        margin=max(2,round(option.fontMetrics.height()*.2));size=view.iconSize()
        area=opt.rect.adjusted(margin,margin,-margin,-margin)
        if is_list:
            icon_rect=QRect(area.left(),area.top()+(area.height()-size.height())//2,size.width(),size.height())
            text_rect=area.adjusted(size.width()+margin*2,0,0,0)
        else:
            icon_rect=QRect(area.center().x()-size.width()//2,area.top(),size.width(),size.height())
            text_rect=area.adjusted(0,size.height()+margin,0,0)
        icon.paint(painter,icon_rect,Qt.AlignCenter,QIcon.Normal,QIcon.On if opt.state&QStyle.State_Selected else QIcon.Off)
        painter.setFont(opt.font);painter.setPen(opt.palette.color(QPalette.Text))
        lines=file_name_lines(text,opt.font,text_rect.width());line_height=opt.fontMetrics.height()
        y=text_rect.top()+max(0,(text_rect.height()-len(lines)*line_height)//2) if is_list else text_rect.top()
        for line in lines:
            painter.drawText(QRect(text_rect.left(),y,text_rect.width(),line_height),Qt.AlignVCenter|(Qt.AlignLeft if is_list else Qt.AlignHCenter),line);y+=line_height
        painter.restore()

    def sizeHint(self,option,index):
        view=option.widget
        if view and view.viewMode()==QListView.ListMode:
            opt=QStyleOptionViewItem(option);self.initStyleOption(opt,index)
            margin=max(2,round(opt.fontMetrics.height()*.2));width=max(1,view.viewport().width()-view.iconSize().width()-margin*4)
            from dpi_support import metric
            return QSize(80,max(metric(34,view.window().ui_factor,18),view.iconSize().height()+margin*2,len(file_name_lines(opt.text,opt.font,width))*opt.fontMetrics.height()+margin*2))
        if view and view.gridSize().isValid():return view.gridSize()
        return super().sizeHint(option,index)


def picture_thumbnail(path,pixels):
    from functools import lru_cache
    try:return _picture_thumbnail(path,os.stat(path).st_mtime_ns,os.stat(path).st_size,pixels)
    except OSError:return None


from functools import lru_cache
@lru_cache(maxsize=96)
def _picture_thumbnail(path,stamp,length,pixels):
    from PyQt5.QtGui import QImageReader,QPixmap,QPainter
    if os.path.splitext(path)[1].lower() not in ('.jpg','.jpeg','.png','.webp','.bmp','.gif','.tif','.tiff','.ico'):return None
    reader=QImageReader(path);reader.setAutoTransform(True);size=reader.size()
    if not size.isValid():return None
    reader.setScaledSize(size.scaled(QSize(pixels,pixels),Qt.KeepAspectRatio));image=reader.read()
    if image.isNull():return None
    image=image.scaled(pixels,pixels,Qt.KeepAspectRatio,Qt.SmoothTransformation)
    result=QPixmap(pixels,pixels);result.fill(Qt.transparent);painter=QPainter(result);painter.drawImage((pixels-image.width())//2,(pixels-image.height())//2,image);painter.end();return result
