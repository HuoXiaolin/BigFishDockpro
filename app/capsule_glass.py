"""Wallpaper-only material shared by the resource capsule and flash controls."""
from types import SimpleNamespace

from PyQt5.QtCore import Qt, QPoint, QRect, QRectF
from PyQt5.QtGui import QPainter, QPainterPath, QPixmap
from PyQt5.QtWidgets import QApplication

from glass_capture import smooth_backdrop
from liquid_glass import material_blur, material_palette, paint_liquid_glass, tint_palette
from wallpaper_source import capture


class CapsuleGlass:
    def __init__(self):
        self.clear()

    def clear(self):
        self.key = None
        self.image = None

    def paint(self, painter, widget, owner, radius, moving=False, appearance=None):
        service = owner.service
        cfg = service.cfg
        style=appearance if appearance is not None else {k:cfg['panel_'+k] for k in ('material','theme','color','opacity','blur','highlight')}
        material=style['material']
        if material == 'clear':
            self.clear()
            return
        rect = QRect(widget.mapToGlobal(QPoint()), widget.size())
        dpr = widget.devicePixelRatioF()
        dock = service.runtime.dock
        mode = style['theme']
        light = dock._sys_light if mode == 'auto' else mode == 'light'
        key = (rect.getRect(), dpr, radius, light, material, style['blur'],
               style['opacity'], style['highlight'], style['color'])
        if self.key != key and (not moving or self.image is None):
            buffer = QPixmap(max(1,round(rect.width()*dpr)),max(1,round(rect.height()*dpr)))
            buffer.setDevicePixelRatio(dpr)
            buffer.fill(Qt.transparent)
            screen = QApplication.screenAt(rect.center()) or QApplication.primaryScreen()
            backdrop = None
            if material != 'solid' and not dock.preview and screen:
                source = SimpleNamespace(frameGeometry=lambda:rect, devicePixelRatioF=lambda:dpr, winId=owner.winId)
                try:
                    backdrop = smooth_backdrop(capture(source,screen),material_blur(style['blur'],material))
                except (OSError,ValueError,RuntimeError,AttributeError):
                    pass
            colors = material_palette(tint_palette(dock.base_theme_colors(mode),style['color']),material)
            strength = style['highlight']/45
            colors['border'].setAlpha(min(255,round(colors['border'].alpha()*strength)))
            stops = [(pos,min(255,round(alpha*strength))) for pos,alpha in dock.merged_grad_stops(colors)]
            surface = SimpleNamespace(cfg={'glass':True,'dock_material':material},backdrop=backdrop,spec_x=0,spec_alpha=0)
            area = QRectF(widget.rect()).adjusted(.8,.8,-.8,-.8)
            path = QPainterPath()
            path.addRoundedRect(area,radius,radius)
            brush = QPainter(buffer)
            brush.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
            paint_liquid_glass(surface,brush,path,area,area,colors,round(style['opacity']*2.55),stops)
            brush.end()
            self.key, self.image = key, buffer
        if self.image is not None:
            painter.drawPixmap(QPoint(), self.image)
