"""A transparent desktop window that paints only the live spectrum."""
from math import ceil, cos, hypot, pi, sin

from PyQt5.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PyQt5.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QApplication, QColorDialog, QWidget

from feature_config import RING_HEIGHT_MAX, SPECTRUM_STYLES
from screen_layout import capture, project, screen_records
from window_edges import BOTTOM, LEFT, RIGHT, TOP, edges_at, paint_edge_targets, resize_cursor, resized_rect


BANDS=120
SILENCE = (0.0,) * BANDS
MIN_WIDTH,MIN_HEIGHT=96,40
SPECTRUM_COLORS=('#4cdddf','#639ffb','#aa83fd','#f38eba','#ffd086')
RING_PADDING=9
GUIDE_RADIUS=.51
BAND_INNER=.61
RING_TRAVEL=.35


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
    for title,value in (('炫彩','colorful'),('单色','mono')):
        action=color.addAction(title)
        action.setCheckable(True)
        action.setChecked(cfg['spectrum_color_mode']==value)
        action.triggered.connect(lambda _,key=value:runtime.set_spectrum_options(spectrum_color_mode=key))
    color.addAction('选择单色…',lambda:choose_mono_color(runtime))
    color.addAction('单色跟随应用主题',lambda:runtime.set_spectrum_options(spectrum_color_mode='mono',spectrum_mono_color=''))
    size=menu.addAction('恢复默认大小',lambda:runtime.set_spectrum_options(spectrum_manual_size=False))
    size.setEnabled(cfg['spectrum_manual_size'] and not cfg['spectrum_locked'])
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
        self.levels = SILENCE
        self.peaks = SILENCE
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
        self.update()

    def reposition(self):
        screens = screen_records()
        if not screens:
            return
        width, height = (264, 264) if self.cfg['spectrum_style'] == 'ring' else (576, 152)
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
        levels=tuple(values[:BANDS]) or SILENCE
        previous=self.peaks if len(self.peaks)==len(levels) else levels
        release=.14 if self.cfg['spectrum_style']=='ring' else .055
        peaks=tuple(max(level,peak-release) for level,peak in zip(levels,previous)) if any(levels) else levels
        if self.levels != levels or self.peaks!=peaks:
            self.levels=levels;self.peaks=peaks
            self.update()

    def showEvent(self, event):
        from window_layers import BOTTOM, restack
        super().showEvent(event)
        restack(int(self.winId()), BOTTOM)

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
        style=self.cfg['spectrum_style']
        if not self.cfg['spectrum_locked']:
            if style=='ring':paint_ring_targets(painter,spectrum_area(self.rect(),style))
            else:paint_edge_targets(painter,self.rect())
        painter.setRenderHint(QPainter.Antialiasing)
        accent = QColor(self.cfg['spectrum_mono_color'] or self.cfg['theme_color'])
        if not accent.isValid():
            accent = QColor('#297bc9' if self.runtime.dock.is_light() else '#78c9ff')
        preview=self.ring_height_preview
        height=self.cfg['spectrum_ring_height'] if preview is None else preview
        draw_spectrum(painter,QRectF(self.rect()),self.levels,style,accent,
                      self.cfg['spectrum_color_mode']=='colorful',self.peaks,ring_height=height,show_limit=preview is not None)
        painter.end()


def draw_spectrum(painter,rect,levels,style,accent,colorful,peaks=None,*,ring_height=100,show_limit=False):
    """Paint bounded strokes only. Peaks advance with the existing audio frames."""
    area=spectrum_area(rect,style)
    if area.isEmpty() or not levels:return
    shades=tuple(map(QColor,SPECTRUM_COLORS)) if colorful else (QColor(accent),)*2
    peaks=levels if peaks is None else peaks
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
        elif style=='mirror':
            width=max(1,step*.40);length=2+level*(height*.43)
            painter.setOpacity(.9);painter.drawRoundedRect(QRectF(x-width/2,middle-length-1,width,length),width/2,width/2)
            painter.setOpacity(.36);painter.drawRoundedRect(QRectF(x-width/2,middle+1,width,length),width/2,width/2)
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
