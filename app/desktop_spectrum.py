"""A transparent desktop window that paints only the live spectrum."""
from math import ceil, cos, pi, sin

from PyQt5.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PyQt5.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QApplication, QColorDialog, QWidget

from feature_config import SPECTRUM_STYLES
from screen_layout import capture, project, screen_records


BANDS=120
SILENCE = (0.0,) * BANDS
MIN_WIDTH,MIN_HEIGHT=96,40
SPECTRUM_COLORS=('#4cdddf','#639ffb','#aa83fd','#f38eba','#ffd086')


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
        self.placement = None
        self.setWindowTitle('桌面音乐频谱 · 大肥鱼Dock')
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setAccessibleDescription('拖动频谱移动，拖动右下角调整大小')

    @property
    def cfg(self):
        return self.runtime.dock.cfg

    def sync(self):
        placement = (self.cfg['spectrum_style'], self.cfg['spectrum_layout'], self.cfg['card_scale'],self.cfg['spectrum_manual_size'])
        if placement != self.placement:
            self.placement = placement
            self.reposition()
        if self.cfg['spectrum_locked']:
            self.drag = None
        self.setCursor(Qt.ArrowCursor if self.cfg['spectrum_locked'] else Qt.SizeAllCursor)
        if not self.isVisible():
            self.show()
        self.update()

    def reposition(self):
        screens = screen_records()
        if not screens:
            return
        width, height = (132, 132) if self.cfg['spectrum_style'] == 'ring' else (288, 76)
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
        self.setGeometry(self.clamped(bounds, center))

    def clamped(self, bounds, point):
        screen = QApplication.screenAt(point) or QApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            bounds.setWidth(min(bounds.width(), area.width()))
            bounds.setHeight(min(bounds.height(), area.height()))
            bounds.moveLeft(max(area.left(), min(bounds.left(), area.right() + 1 - bounds.width())))
            bounds.moveTop(max(area.top(), min(bounds.top(), area.bottom() + 1 - bounds.height())))
        return bounds

    def set_levels(self, values):
        levels=tuple(values[:BANDS]) or SILENCE
        previous=self.peaks if len(self.peaks)==len(levels) else levels
        peaks=tuple(max(level,peak-.055) for level,peak in zip(levels,previous)) if any(levels) else levels
        if self.levels != levels or self.peaks!=peaks:
            self.levels=levels;self.peaks=peaks
            self.update()

    def grip_rect(self):
        return QRect(self.width()-21,self.height()-21,18,18)

    def showEvent(self, event):
        from window_layers import BOTTOM, restack
        super().showEvent(event)
        restack(int(self.winId()), BOTTOM)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.cfg['spectrum_locked']:
            self.drag=QRect(self.geometry()),event.globalPos(),self.grip_rect().contains(event.pos())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drag is None:
            if not self.cfg['spectrum_locked']:
                self.setCursor(Qt.SizeFDiagCursor if self.grip_rect().contains(event.pos()) else Qt.SizeAllCursor)
            return
        start,pointer,resizing=self.drag
        delta=event.globalPos()-pointer
        if resizing:
            screen=QApplication.screenAt(start.center()) or QApplication.primaryScreen()
            area=screen.availableGeometry()
            self.resize(min(area.right()-start.left()+1,max(MIN_WIDTH,start.width()+delta.x())),
                        min(area.bottom()-start.top()+1,max(MIN_HEIGHT,start.height()+delta.y())))
        else:self.move(start.topLeft()+delta)
        event.accept()

    def mouseReleaseEvent(self, event):
        if self.drag is None or event.button() != Qt.LeftButton:
            super().mouseReleaseEvent(event)
            return
        self.mouseMoveEvent(event)
        start,_,resizing=self.drag
        self.drag = None
        if self.geometry()!=start:
            from card_snap import finish_drag
            if not resizing:
                self.setGeometry(self.clamped(self.geometry(), event.globalPos()))
                finish_drag(self, event.globalPos())
            layout = getattr(self.runtime, 'layout', None)
            if not (layout and (layout.pending or layout.applying)):
                anchor = capture(list(self.geometry().getRect()), screen_records())
                if anchor and not self.runtime.set_spectrum_options(spectrum_layout=anchor,
                        spectrum_manual_size=resizing or self.cfg['spectrum_manual_size']):self.setGeometry(start)
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
        painter.setRenderHint(QPainter.Antialiasing)
        accent = QColor(self.cfg['spectrum_mono_color'] or self.cfg['theme_color'])
        if not accent.isValid():
            accent = QColor('#297bc9' if self.runtime.dock.is_light() else '#78c9ff')
        draw_spectrum(painter,QRectF(self.rect()),self.levels,self.cfg['spectrum_style'],accent,
                      self.cfg['spectrum_color_mode']=='colorful',self.peaks)
        if not self.cfg['spectrum_locked']:
            grip=self.grip_rect();painter.fillRect(grip,QColor(0,0,0,1))
            color=QColor('#f7fbff' if not self.runtime.dock.is_light() else '#385d75');color.setAlpha(145 if self.underMouse() else 75)
            painter.setPen(QPen(color,1.15,Qt.SolidLine,Qt.RoundCap))
            for offset in (5,10):
                painter.drawLine(grip.right()-offset,grip.bottom(),grip.right(),grip.bottom()-offset)
        painter.end()


def draw_spectrum(painter,rect,levels,style,accent,colorful,peaks=None):
    """Paint bounded strokes only. Peaks advance with the existing audio frames."""
    area=rect.adjusted(9,7,-9,-7)
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
        draw_orbit(painter,area,levels,peaks,shades)
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


def draw_orbit(painter,area,levels,peaks,shades):
    center=area.center();radius=min(area.width(),area.height())*.48
    weight=max(1.25,radius*.045);count=len(levels)
    orbit=QRectF(center.x()-radius*.51,center.y()-radius*.51,radius*1.02,radius*1.02)
    painter.setBrush(Qt.NoBrush)
    for index,(level,peak) in enumerate(zip(levels,peaks)):
        angle=2*pi*index/count-pi/2
        direction=QPointF(cos(angle),sin(angle))
        color=shades[index*len(shades)//count]
        painter.setOpacity(.32);painter.setPen(QPen(color,max(1,weight*.55),Qt.SolidLine,Qt.RoundCap))
        painter.drawArc(orbit,round((90-index*360/count)*16),-round(360/count*10))
        start=center+direction*(radius*.61);end=center+direction*(radius*(.67+level*.27))
        painter.setPen(QPen(color,weight*2.5,Qt.SolidLine,Qt.RoundCap));painter.setOpacity(.16);painter.drawLine(start,end)
        painter.setPen(QPen(color,weight,Qt.SolidLine,Qt.RoundCap));painter.setOpacity(.94);painter.drawLine(start,end)
        if peak>.1:
            painter.setPen(Qt.NoPen);painter.setBrush(color)
            painter.drawEllipse(center+direction*(radius*(.72+peak*.28)),weight*.55,weight*.55)
            painter.setBrush(Qt.NoBrush)
    painter.setOpacity(1)
