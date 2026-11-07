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
        self.tiny = None

    def paint(self, painter, widget, owner, radius, moving=False, appearance=None, inset=0, shape=None, live=None):
        service = owner.service
        cfg = service.cfg
        style=appearance if appearance is not None else {k:cfg['panel_'+k] for k in ('material','theme','color','opacity','blur','highlight')}
        material=style['material']
        if material == 'clear':
            self.clear()
            return
        rect = QRect(widget.mapToGlobal(QPoint()), widget.size())
        if rect.isEmpty():
            return
        dpr = widget.devicePixelRatioF()
        dock = service.runtime.dock
        mode = style['theme']
        light = dock._sys_light if mode == 'auto' else mode == 'light'
        key = (rect.getRect(), dpr, radius, inset, tuple(shape) if shape else None, live.revision if live else 0, light, material, style['blur'],
               style['opacity'], style['highlight'], style['color'])
        if self.key != key and (not moving or self.image is None or shape or live):
            texture_dpr = dpr * .5 if rect.width()*rect.height()*dpr*dpr > 128*1024 else dpr
            buffer = QPixmap(max(1,round(rect.width()*texture_dpr)),max(1,round(rect.height()*texture_dpr)))
            buffer.fill(Qt.transparent)
            screen = QApplication.screenAt(rect.center()) or QApplication.primaryScreen()
            backdrop = None
            if live and live.image is not None and material!='solid':
                backdrop=QPixmap.fromImage(live.image).scaled(buffer.size(),Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
                backdrop.setDevicePixelRatio(texture_dpr)
            elif moving and shape and self.tiny is not None and material!='solid':
                backdrop=QPixmap.fromImage(self.tiny).scaled(buffer.size(),Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
                backdrop.setDevicePixelRatio(texture_dpr)
            elif material != 'solid' and not dock.preview and screen and not moving:
                source = SimpleNamespace(frameGeometry=lambda:rect, devicePixelRatioF=lambda:dpr, winId=owner.winId)
                try:
                    backdrop = smooth_backdrop(capture(source,screen),material_blur(style['blur'],material))
                except (OSError,ValueError,RuntimeError,AttributeError):
                    pass
                if backdrop is not None and shape:self.tiny=backdrop.toImage().scaled(160,100,Qt.KeepAspectRatio,Qt.SmoothTransformation)
            colors = material_palette(tint_palette(dock.base_theme_colors(mode),style['color']),material)
            strength = style['highlight']/45
            colors['border'].setAlpha(min(255,round(colors['border'].alpha()*strength)))
            stops = [(pos,min(255,round(alpha*strength))) for pos,alpha in dock.merged_grad_stops(colors)]
            surface = SimpleNamespace(cfg={'glass':True,'dock_material':material},backdrop=backdrop,spec_x=0,spec_alpha=0)
            area = QRectF(widget.rect()).adjusted(.8+inset,.8+inset,-.8-inset,-.8-inset)
            if shape:
                from resource_liquid_shape import body_path
                path=body_path(area,shape)
            else:
                path = QPainterPath()
                path.addRoundedRect(area,radius,radius)
            brush = QPainter(buffer)
            brush.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
            # Paint the cache in physical pixels. A subunit pixmap DPR can
            # leave the rounded path at full size and clip it at the cache edge.
            brush.scale(buffer.width() / rect.width(), buffer.height() / rect.height())
            paint_liquid_glass(surface,brush,path,area,area,colors,round(style['opacity']*2.55),stops)
            brush.end()
            self.key, self.image = key, buffer
        if self.image is not None:
            painter.save()
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            painter.drawPixmap(QRectF(widget.rect()), self.image, QRectF(self.image.rect()))
            painter.restore()
