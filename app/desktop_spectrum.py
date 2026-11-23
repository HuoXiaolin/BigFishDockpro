"""A live desktop spectrum with independent backdrop and placement options."""
from math import ceil, cos, exp, hypot, pi, sin, tau
from time import monotonic

from PyQt5.QtCore import QPoint, QPointF, QRect, QRectF, QTimer, Qt
from PyQt5.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PyQt5.QtWidgets import QApplication, QColorDialog, QWidget

from feature_config import RING_HEIGHT_MAX, SPECTRUM_FIXED_PALETTES, SPECTRUM_STYLES
from appearance_presets import dock_appearance
from capsule_glass import CapsuleGlass
from screen_layout import capture, project, screen_records
from spectrum_effects import COLOR_EFFECTS, SPECTRUM_COLORS, sphere_power
from window_edges import BOTTOM, LEFT, RIGHT, TOP, edges_at, paint_edge_targets, resize_cursor, resized_rect
from window_backdrop import component_backdrop, uses_wallpaper


BANDS=120
SILENCE = (0.0,) * BANDS
MIN_WIDTH,MIN_HEIGHT=96,40
SPECTRUM_DEFAULT_SIZES = {
    'ring': (264, 264), 'crown': (440, 230), 'peak_bars': (576, 168), 'particle_sphere': (290, 290),
}
RING_PADDING=9
GUIDE_RADIUS=.51
BAND_INNER=.61
RING_TRAVEL=.35
BAR_PEAK_FALL_RATE = .45
CROWN_ROTATION_SECONDS = 12


def spectrum_area(rect, style):
    top=RING_PADDING if style=='ring' else 7
    return QRectF(rect).adjusted(9,top,-9,-top)


def ring_radius(area):
    return min(area.width(),area.height())*.48


def ring_limit(area):
    return min(area.width(),area.height())/2+RING_PADDING-1


def ring_hit_radii(area):
    radius=ring_radius(area)
    tolerance=min(7,radius*.24)
    return GUIDE_RADIUS*radius-tolerance,(GUIDE_RADIUS+BAND_INNER)*radius/2,ring_limit(area)


def paint_ring_targets(painter, area):
    if area.isEmpty():return
    inner,_,outer=ring_hit_radii(area)
    path=QPainterPath()
    path.addEllipse(area.center(),outer,outer)
    path.addEllipse(area.center(),inner,inner)
    # Alpha 1 preserves a native hit target between the spectrum strokes.
    painter.fillPath(path,QColor(0,0,0,1))


def add_menu_actions(menu, runtime):
    from appearance_presets import APPEARANCE_SOURCES
    cfg = runtime.dock.cfg
    show = menu.addAction('显示桌面音乐频谱')
    show.setCheckable(True)
    show.setChecked(cfg['spectrum_enabled'])
    show.triggered.connect(lambda on: runtime.set_spectrum_options(spectrum_enabled=on))
    styles = menu.addMenu('频谱样式')
    for title, style in SPECTRUM_STYLES:
        action = styles.addAction(title)
        action.setCheckable(True)
        action.setChecked(cfg['spectrum_style'] == style)
        action.triggered.connect(lambda _, value=style: runtime.set_spectrum_options(spectrum_style=value))
    color=menu.addMenu('频谱配色')
    for title,value in APPEARANCE_SOURCES:
        action=color.addAction(title);action.setCheckable(True)
        action.setChecked(cfg['spectrum_appearance_source']==value)
        action.triggered.connect(lambda _,key=value:runtime.set_spectrum_options(spectrum_appearance_source=key))
    color.addSeparator()
    for title,value in (('炫彩','colorful'),('单色','mono')):
        action=color.addAction(title)
        action.setCheckable(True)
        action.setChecked(cfg['spectrum_color_mode']==value)
        action.triggered.connect(lambda _,key=value:runtime.set_spectrum_options(spectrum_color_mode=key))
    color.addAction('选择单色…',lambda:choose_mono_color(runtime))
    color.setEnabled(cfg['spectrum_style'] not in SPECTRUM_FIXED_PALETTES)
    size=menu.addAction('恢复默认大小',lambda:runtime.set_spectrum_options(spectrum_manual_size=False))
    size.setEnabled(cfg['spectrum_manual_size'] and not cfg['spectrum_locked'])
    top=menu.addAction('置顶');top.setCheckable(True);top.setChecked(cfg['spectrum_layer']=='top')
    top.triggered.connect(lambda on:runtime.set_spectrum_options(spectrum_layer='top' if on else 'bottom'))
    from component_passthrough import component_actions
    component_actions(menu.addMenu('鼠标穿透'),runtime,'spectrum')
    lock = menu.addAction('锁定位置')
    lock.setCheckable(True)
    lock.setChecked(cfg['spectrum_locked'])
    lock.triggered.connect(lambda on: runtime.set_spectrum_options(spectrum_locked=on))


def choose_mono_color(runtime):
    cfg=runtime.dock.cfg
    initial=QColor(cfg['spectrum_mono_color'] or cfg['theme_color'] or '#78c9ff')
    color=QColorDialog.getColor(initial,runtime.dock,'桌面频谱单色')
    if color.isValid():runtime.set_spectrum_options(spectrum_color_mode='mono',spectrum_mono_color=color.name())


class DesktopSpectrum(QWidget):
    def __init__(self, runtime):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint)
        self.setProperty('clickThroughKey','spectrum')
        self.runtime = runtime
        self.material = CapsuleGlass()
        self.levels = SILENCE
        self.peaks = SILENCE
        self.bar_peak_time = None
        self.crown_started = None
        self.sphere_time = None
        self.sphere_angle = self.sphere_strength = 0.
        self.animation_timer = QTimer(self)
        self.animation_timer.setInterval(34)
        self.animation_timer.timeout.connect(self.advance_animation)
        self.drag = None
        self.ring_height_preview = None
        self.placement = None
        self.setWindowTitle('桌面音乐频谱 · 大肥鱼Dock')
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setAccessibleDescription('拖动频谱移动，拖动边缘或四角调整大小')

    @property
    def cfg(self):
        return self.runtime.dock.cfg

    def sync(self):
        placement = (self.cfg['spectrum_style'], self.cfg['spectrum_layout'], self.cfg['card_scale'],self.cfg['spectrum_manual_size'])
        if placement != self.placement:
            if self.placement is None or placement[0] != self.placement[0]:
                self.animation_timer.stop()
                self.bar_peak_time = None
                self.crown_started = None
                self.sphere_time = None
                self.sphere_strength = 0.
                if placement[0] == 'peak_bars':
                    self.peaks = self.levels
                elif placement[0] == 'particle_sphere':
                    self.set_levels(self.levels)
            self.placement = placement
            self.drag = self.ring_height_preview = None
            self.reposition()
        if self.cfg['spectrum_locked']:
            self.drag = self.ring_height_preview = None
        self.setAccessibleDescription('左右拖动外环调整直径，上下拖动外环调整跳幅，拖动内圈移动'
                                      if self.cfg['spectrum_style']=='ring' else '拖动频谱移动，拖动边缘或四角调整大小')
        self.setCursor(Qt.ArrowCursor if self.cfg['spectrum_locked'] else Qt.SizeAllCursor)
        if not self.isVisible():
            self.show()
        else:
            self.apply_layer()
        if placement[0] == 'crown' and self.crown_started is None and self.isVisible():
            self.crown_started = monotonic()
            self.animation_timer.start()
        self.update()

    def reposition(self):
        screens = screen_records()
        if not screens:
            return
        width, height = SPECTRUM_DEFAULT_SIZES.get(self.cfg['spectrum_style'], (576, 152))
        scale = self.cfg['card_scale'] / 70
        width, height = round(width * scale), round(height * scale)
        saved = self.cfg['spectrum_layout']
        placement=project(saved,screens,minimum=(1,1)) if saved else None
        if placement:
            bounds=QRect(*placement);center=bounds.center()
            if self.cfg['spectrum_manual_size']:
                width,height=bounds.width(),bounds.height()
        else:
            x, y, w, h = screens[0]['area']
            center = QPoint(x + w - 170, y + h - 114)
        bounds = QRect(0, 0, width, height)
        bounds.moveCenter(center)
        self.setGeometry(self.clamped(bounds, center, square=self.cfg['spectrum_style']=='ring' and not self.cfg['spectrum_manual_size']))

    def clamped(self, bounds, point, *, square=False):
        screen = QApplication.screenAt(point) or QApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            bounds.setWidth(min(bounds.width(), area.width()))
            bounds.setHeight(min(bounds.height(), area.height()))
            if square:
                diameter=min(bounds.width(),bounds.height())
                bounds=QRect(0,0,diameter,diameter)
                bounds.moveCenter(point)
            bounds.moveLeft(max(area.left(), min(bounds.left(), area.right() + 1 - bounds.width())))
            bounds.moveTop(max(area.top(), min(bounds.top(), area.bottom() + 1 - bounds.height())))
        return bounds

    def set_levels(self, values):
        samples=tuple(values[:BANDS])
        levels=samples or SILENCE
        style=self.cfg['spectrum_style']
        if style == 'peak_bars' and samples:
            self.advance_bar_peaks(samples)
            return
        if style == 'particle_sphere':
            self.levels = levels
            if not self.animation_timer.isActive() and sphere_power(self.levels):
                self.sphere_time = monotonic()
                self.animation_timer.start()
            return
        if style == 'crown':
            changed = levels != self.levels
            self.levels = self.peaks = levels
            if changed and not self.animation_timer.isActive():
                self.update()
            return
        if self.animation_timer.isActive():
            self.animation_timer.stop()
        self.bar_peak_time = None
        previous=self.peaks if len(self.peaks)==len(levels) else levels
        release=.14 if style=='ring' else .055
        peaks=tuple(max(level,peak-release) for level,peak in zip(levels,previous)) if any(levels) else levels
        if self.levels==levels and self.peaks==peaks:return
        old_levels=self.levels
        self.levels=levels;self.peaks=peaks
        if style=='mirror':
            if old_levels==levels:return
            area=spectrum_area(self.rect(),style)
            # Include the previous bars so a falling level clears the entire old stroke.
            extent=ceil(5+max(max(old_levels),max(levels))*area.height()*.43)
            self.update(QRectF(area.left()-2,area.center().y()-extent,area.width()+4,2*extent).toAlignedRect())
        else:
            self.update()

    def advance_bar_peaks(self, levels=None):
        if levels is None:
            levels = self.levels
        now = monotonic()
        # The bridge only sends changed samples. Continue falling between frames
        # and stop the timer as soon as the peaks have caught up to the bars.
        elapsed = now - self.bar_peak_time if self.bar_peak_time is not None and self.animation_timer.isActive() else 0
        self.bar_peak_time = now
        previous = self.peaks if len(self.peaks) == len(levels) else levels
        peaks = tuple(max(level, peak - elapsed * BAR_PEAK_FALL_RATE) for level, peak in zip(levels, previous))
        if (levels, peaks) != (self.levels, self.peaks):
            self.levels, self.peaks = levels, peaks
            self.update()
        if peaks == levels:
            self.animation_timer.stop()
        elif not self.animation_timer.isActive():
            self.animation_timer.start()

    def advance_animation(self):
        if self.cfg['spectrum_style'] == 'peak_bars':
            self.advance_bar_peaks()
        elif self.cfg['spectrum_style'] == 'particle_sphere':
            self.advance_sphere()
        elif self.crown_started is not None:
            self.update()
        else:
            self.animation_timer.stop()

    def advance_sphere(self):
        now = monotonic()
        elapsed = 0 if self.sphere_time is None else min(.12, now - self.sphere_time)
        self.sphere_time = now
        target = sphere_power(self.levels)
        # A quick attack follows a beat, while the slower release lets the sphere settle.
        smoothing = .07 if target > self.sphere_strength else .21
        self.sphere_strength += (target - self.sphere_strength) * (1 - exp(-elapsed / smoothing))
        speed = (.65 + 1.55 * self.sphere_strength) * min(1., self.sphere_strength / .16)
        self.sphere_angle = (self.sphere_angle + elapsed * speed) % tau
        if not target and self.sphere_strength < .005:
            self.sphere_strength = 0.
            self.sphere_time = None
            self.animation_timer.stop()
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self.apply_layer()

    def apply_layer(self):
        from window_layers import desktop_layer
        desktop_layer(int(self.winId()), self.cfg['spectrum_layer']=='top')
        self.runtime.click_policy.apply(self)

    def hideEvent(self, event):
        self.material.clear()
        if self.crown_started is not None:
            self.animation_timer.stop()
            self.crown_started = None
        super().hideEvent(event)

    def resize_target(self, pos):
        if self.cfg['spectrum_style']!='ring':return edges_at(self.rect(),pos)
        area=spectrum_area(self.rect(),'ring')
        if area.isEmpty():return 0
        offset=QPointF(pos)-area.center()
        distance=hypot(offset.x(),offset.y())
        _,inner,outer=ring_hit_radii(area)
        if not inner<=distance<=outer:return 0
        if abs(offset.x())>=abs(offset.y()):return LEFT if offset.x()<0 else RIGHT
        return TOP if offset.y()<0 else BOTTOM

    def resize_ring(self, start, pointer, delta, edge):
        area=spectrum_area(start,'ring')
        if edge in (TOP,BOTTOM):
            outward=delta.y() if edge==BOTTOM else -delta.y()
            step=round(outward*100/max(12,ring_radius(area)*RING_TRAVEL))
            self.ring_height_preview=max(0,min(RING_HEIGHT_MAX,self.cfg['spectrum_ring_height']+step))
            self.update()
        else:
            outward=delta.x() if edge==RIGHT else -delta.x()
            if not outward:
                self.setGeometry(start)
                return
            span=min(area.width(),area.height())
            grab_distance=max(1,abs(pointer.x()-area.center().x()))
            diameter=max(MIN_HEIGHT,round(span*(1+outward/grab_distance))+2*RING_PADDING)
            bounds=QRect(0,0,diameter,diameter)
            bounds.moveCenter(start.center())
            self.setGeometry(self.clamped(bounds,start.center(),square=True))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.cfg['spectrum_locked']:
            self.drag=QRect(self.geometry()),event.globalPos(),self.resize_target(event.pos())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drag is None:
            if not self.cfg['spectrum_locked']:
                self.setCursor(resize_cursor(self.resize_target(event.pos())))
            return
        start,pointer,edges=self.drag
        delta=event.globalPos()-pointer
        if edges and self.cfg['spectrum_style']=='ring':
            self.resize_ring(start,pointer,delta,edges)
        elif edges:
            self.setGeometry(resized_rect(start,edges,delta,(MIN_WIDTH,MIN_HEIGHT)))
        else:self.move(start.topLeft()+delta)
        event.accept()

    def mouseReleaseEvent(self, event):
        if self.drag is None or event.button() != Qt.LeftButton:
            super().mouseReleaseEvent(event)
            return
        self.mouseMoveEvent(event)
        start,_,edges=self.drag
        self.drag = None
        height=self.ring_height_preview
        self.ring_height_preview=None
        if height is not None:
            if height!=self.cfg['spectrum_ring_height']:
                self.runtime.set_spectrum_options(spectrum_ring_height=height)
            self.update()
        elif self.geometry()!=start:
            from card_snap import finish_drag
            if not edges:
                self.setGeometry(self.clamped(self.geometry(), event.globalPos()))
                finish_drag(self, event.globalPos())
            layout = getattr(self.runtime, 'layout', None)
            if not (layout and (layout.pending or layout.applying)):
                anchor = capture(list(self.geometry().getRect()), screen_records())
                if anchor and not self.runtime.set_spectrum_options(spectrum_layout=anchor,
                        spectrum_manual_size=bool(edges) or self.cfg['spectrum_manual_size']):self.setGeometry(start)
        if not self.cfg['spectrum_locked']:
            self.setCursor(resize_cursor(self.resize_target(self.mapFromGlobal(event.globalPos()))))
        event.accept()

    def contextMenuEvent(self, event):
        from ui_style import AlignedMenu
        menu = AlignedMenu(self.runtime.dock)
        add_menu_actions(menu, self.runtime)
        menu.exec_(event.globalPos())
        menu.deleteLater()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.transparent)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        style = self.cfg['spectrum_style']
        appearance = dock_appearance(self.cfg)
        mode = component_backdrop(self.cfg, 'spectrum')
        if uses_wallpaper(mode, appearance):
            self.paint_wallpaper_spectrum(painter, style, appearance)
        else:
            if self.material.uses_wallpaper:
                self.material.clear()
                self.material.uses_wallpaper = False
            self.paint_spectrum(painter, style)
        if not self.cfg['spectrum_locked']:
            if style=='ring':paint_ring_targets(painter,spectrum_area(self.rect(),style))
            else:paint_edge_targets(painter,self.rect())
        painter.end()

    def paint_wallpaper_spectrum(self, painter, style, appearance):
        dpr = self.devicePixelRatioF()
        ink = QPixmap(round(self.width() * dpr), round(self.height() * dpr))
        ink.setDevicePixelRatio(dpr)
        ink.fill(Qt.transparent)
        frame = QPainter(ink)
        self.paint_spectrum(frame, style)
        frame.end()

        # Show wallpaper only through the frequency graphics' existing alpha.
        # Transparent space around the sphere, ring and bars stays transparent.
        self.material.paint(painter, self, self.runtime.dock, 0, self.drag is not None, appearance)
        painter.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        painter.drawPixmap(QRectF(self.rect()), ink, QRectF(ink.rect()))
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.drawPixmap(QRectF(self.rect()), ink, QRectF(ink.rect()))

    def paint_spectrum(self, painter, style):
        painter.setRenderHint(QPainter.Antialiasing)
        following=self.cfg.get('spectrum_appearance_source')=='app'
        accent = QColor(self.cfg['theme_color'] if following else self.cfg['spectrum_mono_color'] or self.cfg['theme_color'])
        if not accent.isValid():
            accent = QColor('#297bc9' if self.runtime.dock.is_light() else '#78c9ff')
        preview=self.ring_height_preview
        height=self.cfg['spectrum_ring_height'] if preview is None else preview
        crown_angle = 0.
        if style == 'crown' and self.crown_started is not None:
            crown_angle = (monotonic() - self.crown_started) % CROWN_ROTATION_SECONDS * tau / CROWN_ROTATION_SECONDS
        draw_spectrum(painter,QRectF(self.rect()),self.levels,style,accent,
                      not following and self.cfg['spectrum_color_mode']=='colorful',self.peaks,ring_height=height,
                      show_limit=preview is not None,crown_angle=crown_angle,
                      sphere_angle=self.sphere_angle,sphere_strength=self.sphere_strength)


def draw_spectrum(painter,rect,levels,style,accent,colorful,peaks=None,*,ring_height=100,show_limit=False,
                  crown_angle=0.,sphere_angle=0.,sphere_strength=None):
    """Paint bounded strokes only. Peaks advance with the existing audio frames."""
    area=spectrum_area(rect,style)
    if area.isEmpty() or not levels:return
    peaks=levels if peaks is None else peaks
    effect = COLOR_EFFECTS.get(style)
    if effect is not None:
        painter.save()
        try:
            painter.setClipRect(area, Qt.IntersectClip)
            if style == 'particle_sphere':
                effect(painter, area, levels, peaks, rotation=sphere_angle, power=sphere_strength)
            elif style == 'crown':
                effect(painter, area, levels, peaks, rotation=crown_angle)
            else:
                effect(painter, area, levels, peaks)
        finally:
            painter.restore()
        return
    shades=tuple(map(QColor,SPECTRUM_COLORS)) if colorful else (QColor(accent),)*2
    span=min(area.width(),area.height())*1.85 if style=='ring' else area.width()
    count=max(3,min(len(levels),int(span/(5 if style=='dots' else 2.3))))
    if count<len(levels):
        edges=[i*len(levels)//count for i in range(count+1)]
        levels=tuple(max(levels[a:b]) for a,b in zip(edges,edges[1:]))
        peaks=tuple(max(peaks[a:b]) for a,b in zip(edges,edges[1:]))
    if style=='ring':
        draw_orbit(painter,area,levels,peaks,shades,ring_height,show_limit)
        return

    gradient=QLinearGradient(area.left(),0,area.right(),0)
    for index,color in enumerate(shades):gradient.setColorAt(index/(len(shades)-1),color)
    brush=QBrush(gradient);height=area.height();step=area.width()/len(levels)
    bottom=area.bottom()-2;middle=area.center().y()
    if style=='line':
        draw_ribbons(painter,area,levels,brush)
        return

    if style=='mirror':
        painter.setOpacity(.25);painter.setPen(QPen(brush,1))
        painter.drawLine(QPointF(area.left(),middle),QPointF(area.right(),middle))
        width=max(1,step*.40);radius=width/2
        bars=[(area.left()+(i+.5)*step-radius,2+level*(height*.43)) for i,level in enumerate(levels)]
        painter.setPen(Qt.NoPen);painter.setBrush(brush)
        painter.setOpacity(.9)
        for x,length in bars:
            painter.drawRoundedRect(QRectF(x,middle-length-1,width,length),radius,radius)
        painter.setOpacity(.36)
        for x,length in bars:
            painter.drawRoundedRect(QRectF(x,middle+1,width,length),radius,radius)
        painter.setOpacity(1)
        return
    painter.setPen(Qt.NoPen);painter.setBrush(brush)
    for index,(level,peak) in enumerate(zip(levels,peaks)):
        x=area.left()+(index+.5)*step
        if style=='dots':
            active=ceil(level*7)
            radius=max(1,min(step*.27,height*.056))
            for row in range(8):
                y=bottom-radius-row*(height-radius*2-4)/7
                painter.setOpacity(.16 if row>active else .48+.07*row)
                painter.drawEllipse(QPointF(x,y),radius,radius)
        else:
            width=max(1,step*.54);length=3+level*(height-9)
            painter.setOpacity(.15);painter.drawRoundedRect(QRectF(x-width*.68,bottom-length-1,width*1.36,length+2),width/2,width/2)
            painter.setOpacity(.9);painter.drawRoundedRect(QRectF(x-width/2,bottom-length,width,length),width/2,width/2)
            if peak>.06:
                y=bottom-5-peak*(height-9)
                painter.setOpacity(.9);painter.drawRoundedRect(QRectF(x-width/2,y,width,1.8),.9,.9)
    painter.setOpacity(1)


def draw_ribbons(painter,area,levels,brush):
    height=area.height();step=area.width()/len(levels)

    def ribbon(base,amplitude):
        points=[QPointF(area.left()+(index+.5)*step,area.top()+height*(base-level*amplitude))
                for index,level in enumerate(levels)]
        path=QPainterPath(points[0])
        for left,right in zip(points,points[1:]):
            middle=(left.x()+right.x())/2
            path.cubicTo(middle,left.y(),middle,right.y(),right.x(),right.y())
        return path

    core=ribbon(.83,.63);weight=min(5,max(1.6,step*.18))
    for path,width,opacity in ((ribbon(.92,.36),weight*.65,.46),(core,weight*3,.13),(core,weight,1)):
        painter.setOpacity(opacity);painter.setPen(QPen(brush,width,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
        painter.drawPath(path)


def ring_strength(level, treble_lift):
    # Lift weak upper bands without clipping strong readings or generating activity in silence.
    balanced = level * (1 + treble_lift) / (1 + level * treble_lift)
    amount = max(0., (balanced - .12) / .88)
    return amount * amount * (3 - 2 * amount)


def draw_orbit(painter,area,levels,peaks,shades,height,show_limit):
    center = area.center()
    radius = ring_radius(area)
    count = len(levels)
    bar_start = radius * BAND_INNER
    bar_base = bar_start + radius * .01
    pitch = 2 * pi * bar_start / count
    weight = max(.7, min(radius * .028, pitch * .62))
    dot_radius = weight * .48
    peak_base = radius * (1 - RING_TRAVEL)
    travel = radius * RING_TRAVEL * min(100, height) / 100
    if height > 100:
        reach = ring_limit(area) - dot_radius
        travel += (reach - radius) * (height - 100) / (RING_HEIGHT_MAX - 100)
    if show_limit:
        painter.setPen(QPen(shades[0], 1, Qt.DashLine))
        painter.setBrush(Qt.NoBrush)
        painter.setOpacity(.52)
        limit = peak_base + travel
        painter.drawEllipse(center, limit, limit)
    guide = radius * GUIDE_RADIUS
    orbit = QRectF(center.x() - guide, center.y() - guide, 2 * guide, 2 * guide)
    painter.setBrush(Qt.NoBrush)
    for index, (level, peak) in enumerate(zip(levels, peaks)):
        color = shades[index * len(shades) // count]
        painter.setOpacity(.32)
        painter.setPen(QPen(color, max(1, weight * .55), Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(orbit, round((90 - index * 360 / count) * 16), -round(360 / count * 10))

        treble_lift = max(0., 2 * index / max(1, count - 1) - 1)
        level = ring_strength(level, treble_lift)
        peak = ring_strength(peak, treble_lift)
        if not (level or peak):
            continue
        angle = 2 * pi * index / count - pi / 2
        direction = QPointF(cos(angle), sin(angle))
        if level:
            start = center + direction * bar_start
            end = center + direction * (bar_base + travel * level)
            painter.setPen(QPen(color, weight * 1.4, Qt.SolidLine, Qt.RoundCap))
            painter.setOpacity(.14 * level)
            painter.drawLine(start, end)
            painter.setPen(QPen(color, weight, Qt.SolidLine, Qt.RoundCap))
            painter.setOpacity(.22 + .74 * min(1, level * 2))
            painter.drawLine(start, end)
        if peak > .1:
            painter.setOpacity(.35 + .59 * peak)
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(center + direction * (peak_base + travel * peak), dot_radius, dot_radius)
            painter.setBrush(Qt.NoBrush)
    painter.setOpacity(1)
