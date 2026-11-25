"""Render unsaved Dock settings against a stable Windows desktop scene."""
import os
from pathlib import Path
from types import SimpleNamespace

from PyQt5.QtCore import QRectF, QSize, Qt
from PyQt5.QtGui import QColor, QFont, QImageReader, QPainter, QPainterPath, QPixmap
from PyQt5.QtWidgets import QStyle, QWidget

from calendar_almanac import ASSETS
from appearance_presets import MATERIALS
from dock_icon_shape import circular_icon
from glass_capture import smooth_backdrop
from liquid_glass import dock_theme_colors, material_blur
from ui_style import widget_px


class DockPreview(QWidget):
    keys=('theme','dock_material','theme_color','dock_highlight','transparency','blur_px','glass',
          'clear_background','icon_size','dock_icon_shape','position')

    def __init__(self, dialog):
        super().__init__()
        self.dialog=dialog
        self.dock=dialog.tray.dock
        self.setObjectName('SettingsPreview')
        self.setAccessibleName('Dock 外观实时预览')
        self.setFixedHeight(138)
        self._scene_key=self._blur_key=None
        self._scene=self._blurred=QPixmap()
        self._icons=[item['pixmap'] for item in self.dock.items if item.get('pixmap') and not item['pixmap'].isNull()][:5]
        windows=Path(os.environ.get('SystemRoot','C:/Windows'))
        for source in (windows/'explorer.exe',ASSETS.parent/'dock.ico',windows/'System32'/'notepad.exe',
                       windows/'System32'/'Taskmgr.exe',windows/'System32'/'charmap.exe'):
            if len(self._icons)==5:break
            if source.is_file():
                pixmap=self.dock.icons.get(str(source),72)
                if not pixmap.isNull():self._icons.append(pixmap)
        if not self._icons:self._icons.append(self.style().standardIcon(QStyle.SP_DirIcon).pixmap(72,72))
        self._round_icons=None
        self.source=windows/'Web/Wallpaper/Windows/img0.jpg'
        if not self.source.is_file():self.source=ASSETS/'pictures'/'summer-5.jpg'
        for key in self.keys:
            dialog.change_signal(dialog.fields[key]).connect(self.update)

    def sizeHint(self):
        return QSize(widget_px(self,420),widget_px(self,138))

    def scene(self, blur):
        dpr=self.devicePixelRatioF()
        physical=self.size()*dpr
        key=(physical.width(),physical.height(),dpr)
        if key!=self._scene_key:
            reader=QImageReader(str(self.source))
            original=reader.size()
            if original.isValid():
                reader.setScaledSize(original.scaled(physical,Qt.KeepAspectRatioByExpanding))
            source=QPixmap.fromImage(reader.read())
            if source.isNull():
                source=QPixmap(physical);source.fill(QColor('#7ca7bc'))
            x=max(0,(source.width()-physical.width())//2)
            y=max(0,(source.height()-physical.height())//2)
            self._scene=source.copy(x,y,physical.width(),physical.height())
            self._scene.setDevicePixelRatio(dpr)
            self._scene_key=key;self._blur_key=None
        if blur!=self._blur_key:
            self._blurred=smooth_backdrop(self._scene,blur) if blur else self._scene
            self._blur_key=blur
        return self._scene

    def paintEvent(self,event):
        cfg={key:self.dialog.field_value(key,self.dialog.fields[key]) for key in self.keys}
        if not QColor(cfg['theme_color']).isValid():cfg['theme_color']=''
        material=cfg['dock_material']
        colors=dock_theme_colors(cfg,self.dock._sys_light)
        samples_wallpaper=cfg['glass'] and not cfg['clear_background'] and material not in ('clear','solid')
        blur=material_blur(cfg['blur_px'],material) if samples_wallpaper else 0
        p=QPainter(self);p.setRenderHints(QPainter.Antialiasing|QPainter.SmoothPixmapTransform)
        frame=QRectF(self.rect())
        clip=QPainterPath();clip.addRoundedRect(frame,10,10);p.setClipPath(clip)
        p.drawPixmap(0,0,self.scene(blur))
        h=frame.height();w=frame.width()
        size=min(w/7.5,h*.42,max(h*.19,h*.28*(cfg['icon_size']/48)**.52))
        gap=size*.36
        length=(size+gap)*len(self._icons)+gap
        bar_h=size*1.60
        top=cfg['position']=='top'
        y=h*.12 if top else h-h*.12-bar_h
        bar=QRectF((w-length)/2,y,length,bar_h)
        radius=min(bar_h*.5,max(8,bar_h*colors['corner']))
        path=QPainterPath();path.addRoundedRect(bar,radius,radius)
        surface=SimpleNamespace(cfg=cfg,backdrop=self._blurred if samples_wallpaper else None,spec_alpha=0.)
        self.dock.paint_dock_surface(surface,p,[path],bar,colors)
        icons=self._icons
        if cfg['dock_icon_shape']=='circle':
            if self._round_icons is None:self._round_icons=[circular_icon(pm,72) for pm in icons]
            icons=self._round_icons
        for i,icon in enumerate(icons):
            rect=QRectF(bar.left()+gap+i*(size+gap),bar.center().y()-size/2,size,size)
            p.drawPixmap(rect,icon,QRectF(icon.rect()))
        material_label=self.dialog.fields['dock_material'].currentText()
        if material_label=='自定义材质':
            material_label=next((name for name,key in MATERIALS if key==material),material_label)
        description='全透明' if cfg['clear_background'] else f'{material_label}  ·  不透明度 {100-cfg["transparency"]}%'
        font=QFont(self.font());font.setPixelSize(max(10,round(h*.085)));p.setFont(font)
        label=QRectF(10,h-29 if top else 9,p.fontMetrics().horizontalAdvance(description)+16,20)
        p.setPen(Qt.NoPen);p.setBrush(QColor(16,25,38,185));p.drawRoundedRect(label,6,6)
        p.setPen(Qt.white);p.drawText(label,Qt.AlignCenter,description)
