"""Adaptive text colors for desktop widgets, independent of the frame."""
from functools import lru_cache
from math import ceil
from weakref import WeakSet

from PyQt5.QtCore import QEvent, QObject, QRectF, QTimer, Qt
from PyQt5.QtGui import QColor, QImage, QPainter, QPainterPath, QPixmap

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
        self.live = False
        self.texture = None
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
            self.timer.start(100)
        elif event.type() == QEvent.Hide:
            self.timer.stop()
        return False

    def measure(self):
        from window_backdrop import desktop_backdrop
        mode, app_light, fallback_light, material, theme, tint, opacity, highlight, system_light, design, solid, desktop_fallback, _ = self.spec
        if solid:
            layers = (QColor(solid).getRgb(),)*128
        else:
            layers = _glass_samples(material,theme,tint,opacity,highlight,system_light,design)
        fallback = (235,238,242) if fallback_light else (30,35,40)
        pixels = None
        diagnostics=getattr(self.widget,'capsule_diagnostics',None)
        sources=[] if diagnostics is not None else None
        sampled=None
        app_cells=0
        paper_source=None
        needs_background = mode == 'auto' and any(layer[3]<250 for layer in layers)
        self.live = needs_background and desktop_backdrop(self.widget,self.dock.cfg) == 'dynamic'
        if needs_background:
            try:
                # Never create a native HWND for an embedded label or card.
                from capsule_scale import native_host, widget_rect
                top = native_host(self.widget)
                rect = widget_rect(top,self.widget,self.widget.rect()).toAlignedRect()
                if self.live:
                    from desktop_underlay import window_samples
                    pixels = window_samples(top, rect, sources=sources)
                    if diagnostics is not None and pixels:
                        sampled=pixels
                        app_cells=sum(color is not None for color in pixels)
                if pixels is None or None in pixels:
                    try:paper = wallpaper_samples(top,rect,allow_fallback=desktop_fallback)
                    except OSError:paper = None
                    if paper:
                        paper = tuple(paper[y*32+x] for y in range(8) for x in range(16))
                        paper_source='壁纸或系统桌面底色'
                    elif desktop_fallback:
                        from desktop_underlay import exposed_wallpaper_samples
                        paper = exposed_wallpaper_samples(top,rect)
                        if paper:paper_source='同一屏幕上可见的桌面像素'
                    paper = paper or (fallback,)*128
                    pixels = tuple(color if color is not None else paper[i] for i,color in enumerate(pixels)) if pixels else paper
                    if diagnostics is not None and paper_source:sampled=pixels
            except (OSError, ValueError, RuntimeError, AttributeError):
                pass
        measurement = self.spec, pixels
        if self.last_measurement == measurement and self.result is not None:
            if diagnostics is not None:
                diagnostics.record_colors(self.widget,sampled,app_cells,paper_source,self.surface_samples,
                                          self.result,mode,needs_background,self.live,sources)
            return self.result
        self.last_measurement = measurement
        samples = [blend(layer[:3], (pixels[i] if pixels else None) or fallback, layer[3]/255)
                   for i,layer in enumerate(layers)]
        if self.regional:
            self.surface_samples = tuple(tuple(round(v) for v in sample) for sample in samples)
            self.regions.clear()
            self.texture = None
        representative=majority_surface(samples)
        if mode=='auto':
            light=contrast(representative,'#000000')>=contrast(representative,'#ffffff')
        else:
            light=app_light if mode=='app' else mode=='light'
        self.ink_background=representative if self.uses_custom_ink else None
        if diagnostics is not None:
            diagnostics.record_colors(self.widget,sampled,app_cells,paper_source,samples,light,mode,needs_background,self.live,sources)
        return light

    def sample_texture(self):
        """Low-resolution input for the clock's own material and typography renderer."""
        if self.texture is None and self.surface_samples:
            data = bytes(channel for color in self.surface_samples for channel in color)
            self.texture = QPixmap.fromImage(QImage(data,16,8,48,QImage.Format_RGB888))
        return self.texture

    def background_at(self, rect):
        if not self.surface_samples or not self.spec or self.spec[0]!='auto':return None
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
        if self.live and self.widget is not None and self.widget.isVisible():
            self.timer.start(900)


def content_contrast(widget, dock, style, mode, callback, *, design=None, solid=None, custom_ink=False, regional=False):
    from window_backdrop import desktop_backdrop
    state = getattr(widget,'_content_contrast',None)
    if state is None:
        state = widget._content_contrast = ContentContrast(widget)
    app_light = dock.base_theme_colors(dock.cfg.get('theme','auto'))['light']
    theme = style.get('theme','auto')
    spec = (mode, app_light, dock.base_theme_colors(theme)['light'],style['material'],theme,style.get('color',''),
            style.get('opacity',0),style.get('highlight',0),bool(dock._sys_light),design,solid,not getattr(dock,'preview',False),
            desktop_backdrop(widget,dock.cfg) if mode=='auto' else None)
    state.callback = callback
    state.dock = dock
    if state.spec != spec or state.uses_custom_ink!=custom_ink or state.regional!=regional:
        state.regional = regional
        state.uses_custom_ink = custom_ink
        state.last_measurement = None
        state.spec = spec
        state.result = state.measure()
        if state.live and widget.isVisible():
            state.timer.start(900)
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


def transparent_surface(widget, dock, enabled):
    """Observe only the ground when a renderer applies its own colors or material."""
    if enabled:
        content_contrast(widget,dock,{'theme':'auto','material':'clear'},'auto',widget.update,regional=True)
        return widget._content_contrast
    state = getattr(widget,'_content_contrast',None)
    if state is not None and state.spec is not None:
        state.spec = None
        state.live = False
        state.surface_samples = ()
        state.texture = None
        state.regions.clear()
        state.timer.stop()
    return None


@lru_cache(maxsize=512)
def graphic_ink(color, background, minimum=3):
    from clock_legibility import readable
    return readable(QColor(color),[QColor(*background)],minimum).name() if background else color


def refresh_visible(live_only=False):
    for state in tuple(_windows):
        if state.spec and (not live_only or state.live) and state.widget.isVisible() and (
                not state.timer.isActive() or state.timer.remainingTime()>100):
            state.timer.start(100)
