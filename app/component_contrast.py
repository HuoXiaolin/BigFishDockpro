"""Adaptive text colors for desktop widgets, independent of the frame."""
from functools import lru_cache
from math import ceil
from weakref import WeakSet

from PyQt5.QtCore import QEvent, QObject, QRectF, QTimer, Qt
from PyQt5.QtGui import QColor, QImage, QPainter, QPainterPath

from background_contrast import blend, contrast, majority_surface, wallpaper_samples


_windows = WeakSet()


@lru_cache(maxsize=48)
def _glass_samples(material, theme, tint, opacity, highlight, system_light, design):
    from types import SimpleNamespace
    from liquid_glass import base_theme_colors, material_palette, paint_liquid_glass, tint_palette
    from card_design import paint_design
    from liquid_glass import merged_grad_stops
    colors = material_palette(tint_palette(base_theme_colors(theme, system_light), tint), material)
    image = QImage(64, 40, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    if material != 'clear':
        p = QPainter(image)
        rect = QRectF(image.rect())
        path = QPainterPath()
        path.addRect(rect)
        surface = SimpleNamespace(cfg=dict(glass=False, live_backdrop=True, dock_material=material),
                                  spec_alpha=0, spec_x=0, backdrop=None)
        stops = [(pos, min(255, round(a*highlight/45))) for pos,a in merged_grad_stops(colors)]
        try:
            paint_liquid_glass(surface,p,path,rect,rect,colors,round(2.55*opacity),stops)
            if design:
                paint_design(p,rect,dict(theme_color=tint,card_design=design),design,body_top=12,header_separator=False)
        finally:
            p.end()
    return tuple(image.pixelColor(2+4*x,2+round(35*y/7)).getRgb() for y in range(8) for x in range(16))


class ContentContrast(QObject):
    def __init__(self, widget):
        super().__init__(widget)
        self.widget = widget
        self.spec = self.result = None
        self.last_measurement = None
        self.ink_background = None
        self.uses_custom_ink = False
        self.surface_samples = ()
        self.regional = False
        self.region_size = None
        self.regions = {}
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.refresh)
        widget.installEventFilter(self)
        widget.destroyed.connect(self.retire)
        _windows.add(self)

    def retire(self):
        _windows.discard(self)
        self.callback = None
        self.widget = None

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Show,QEvent.Move,QEvent.Resize) and self.spec:
            if not self.timer.isActive():self.timer.start(120)
        elif event.type() == QEvent.Hide:
            self.timer.stop()
        return False

    def measure(self):
        mode, app_light, fallback_light, material, theme, tint, opacity, highlight, system_light, design, solid, desktop_fallback = self.spec
        if solid:
            layers = (QColor(solid).getRgb(),)*128
        else:
            layers = _glass_samples(material,theme,tint,opacity,highlight,system_light,design)
        fallback = (235,238,242) if fallback_light else (30,35,40)
        pixels = None
        if any(layer[3]<250 for layer in layers):
            try:
                # Never create a native HWND for an embedded label or card.
                top = self.widget.window()
                rect = self.widget.rect()
                rect.moveTopLeft(self.widget.mapTo(top,rect.topLeft()))
                pixels = wallpaper_samples(top,rect,allow_fallback=desktop_fallback)
            except (OSError, ValueError, RuntimeError, AttributeError):
                pass
        measurement = self.spec, pixels
        if self.last_measurement == measurement and self.result is not None:
            return self.result
        self.last_measurement = measurement
        samples = [blend(layer[:3], pixels[(i//16)*32+i%16] if pixels else fallback, layer[3]/255)
                   for i,layer in enumerate(layers)]
        if self.regional:
            self.surface_samples = tuple(tuple(round(v) for v in sample) for sample in samples)
            self.regions.clear()
        representative=majority_surface(samples)
        if mode=='auto':
            light=contrast(representative,'#000000')>=contrast(representative,'#ffffff')
        else:
            light=app_light if mode=='app' else mode=='light'
        self.ink_background=representative if self.uses_custom_ink else None
        return light

    def background_at(self, rect):
        if not self.surface_samples or self.spec[0]!='auto':return None
        width,height=max(1,self.widget.width()),max(1,self.widget.height())
        left=max(0,min(15,int(rect.left()*16/width)))
        right=max(left+1,min(16,ceil(rect.right()*16/width)))
        top=max(0,min(7,int(rect.top()*8/height)))
        bottom=max(top+1,min(8,ceil(rect.bottom()*8/height)))
        key=left,right,top,bottom
        if key not in self.regions:
            self.regions[key]=majority_surface([self.surface_samples[y*16+x] for y in range(top,bottom) for x in range(left,right)])
        return self.regions[key]

    def refresh(self):
        if self.widget is None or not self.widget.isVisible() or not self.spec:return
        previous=self.surface_samples
        previous_ink=self.ink_background
        result = self.measure()
        size=self.widget.size() if self.regional else None
        if result != self.result or self.surface_samples!=previous or self.ink_background!=previous_ink or size!=self.region_size:
            self.result = result
            self.region_size=size
            self.callback()


def content_contrast(widget, dock, style, mode, callback, *, design=None, solid=None, custom_ink=False, regional=False):
    state = getattr(widget,'_content_contrast',None)
    if state is None:
        state = widget._content_contrast = ContentContrast(widget)
    app_light = dock.base_theme_colors(dock.cfg.get('theme','auto'))['light']
    theme = style.get('theme','auto')
    spec = (mode, app_light, dock.base_theme_colors(theme)['light'],style['material'],theme,style.get('color',''),
            style.get('opacity',0),style.get('highlight',0),bool(dock._sys_light),design,solid,not getattr(dock,'preview',False))
    state.callback = callback
    if state.spec != spec or state.uses_custom_ink!=custom_ink or state.regional!=regional:
        state.regional = regional
        state.uses_custom_ink = custom_ink
        state.last_measurement = None
        state.spec = spec
        state.result = state.measure()
    return state.result


def card_text_ink(custom, light, background):
    """Keep the author's ink when label-size text is legible across the card."""
    neutral = '#101b25' if light else '#ffffff'
    if custom and background is not None:
        ink = QColor(custom)
        darker = contrast(ink.getRgb()[:3],'#000000') < contrast(background,'#000000')
        if darker==light and contrast(background,custom)>=4.5:
            return ink
    return QColor(neutral)


def refresh_visible():
    for state in tuple(_windows):
        if state.widget.isVisible() and not state.timer.isActive():
            state.timer.start(100)
