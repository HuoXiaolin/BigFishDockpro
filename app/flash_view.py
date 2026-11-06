"""Native drawing for flash colours, compact rows and direct text input."""
from PyQt5.QtCore import Qt, QRectF, QRect, QSize, QPointF, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPen, QPainterPath, QIcon, QPixmap
from PyQt5.QtWidgets import (QApplication, QStyle, QStyledItemDelegate, QListWidget,
                             QToolButton, QPlainTextEdit, QAbstractItemView,QListView,QFrame)
from flash_data import COLORS, MAX_TEXT


def blend(a,b,part):
    a,b=QColor(a),QColor(b)
    return QColor.fromRgbF(*(x*(1-part)+y*part for x,y in zip(a.getRgbF()[:3],b.getRgbF()[:3])))


def text_ink(color):
    def linear(c):
        return c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4
    color=QColor(color)
    luminance=sum(w*linear(c) for w,c in zip((.2126,.7152,.0722),color.getRgbF()[:3]))
    return '#101418' if luminance>.20 else '#ffffff'


def palette_for(service,background=None):
    cfg=service.cfg
    theme=background['theme'] if background is not None else cfg['panel_theme']
    light=theme=='light' or (theme=='auto' and service.runtime.dock._sys_light)
    surface='#f7f9fb' if light else '#26292d'
    accent=(background['color'] if background is not None else cfg['panel_color']) or '#9ac6e0'
    return dict(light=light,surface=surface, field='#ffffff' if light else '#303439',
                ink='#18232d' if light else '#ffffff', muted='#526373' if light else '#bdc9d2',
                line='#cfdae3' if light else '#4b5259', hover='#e4ebf0' if light else '#39414a',
                fills={key:(rgb if cfg['flash_palette']=='vivid' else
                       blend(blend(rgb,accent,.15),surface,.73 if light else .76).name())
                       for key,(_,rgb) in COLORS.items()})


def icon(name,ink,side=17):
    ratio=max(2.,QApplication.primaryScreen().devicePixelRatio())
    pm=QPixmap(round(side*ratio),round(side*ratio));pm.setDevicePixelRatio(ratio);pm.fill(Qt.transparent)
    painter=QPainter(pm);painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(side/24,side/24)
    pen=QPen(QColor(ink),1.65,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin);painter.setPen(pen)
    def line(points,close=False):
        path=QPainterPath(QPointF(*points[0]))
        for point in points[1:]:path.lineTo(*point)
        if close:path.closeSubpath()
        painter.drawPath(path)
    if name=='flash':line([(14,2),(5,14),(11,14),(10,22),(20,9),(13,9)],True)
    elif name=='more':
        painter.setPen(Qt.NoPen);painter.setBrush(QColor(ink))
        for x in (5,12,19):painter.drawEllipse(QPointF(x,12),1.6,1.6)
    elif name=='filter':line([(3,4),(21,4),(14,12),(14,19),(10,21),(10,12)],True)
    elif name=='search':
        painter.drawEllipse(QRectF(4,4,12,12));line([(14,14),(21,21)])
    elif name=='pin':
        line([(8,3),(17,3),(15,7),(15,11),(18,14),(6,14),(9,11),(9,7)],True);line([(12,14),(12,21)])
    elif name=='copy':
        painter.drawRoundedRect(QRectF(8,8,12,13),2,2);line([(15,5),(15,3),(4,3),(4,16),(6,16)])
    elif name=='edit':
        line([(4,20),(9,19),(20,8),(16,4),(5,15)],True);line([(13,7),(17,11)])
    elif name=='trash':
        line([(4,7),(20,7)]);line([(9,7),(9,4),(15,4),(15,7)]);line([(7,7),(8,20),(16,20),(17,7)])
    elif name=='bell':
        path=QPainterPath(QPointF(5,17));path.cubicTo(9,13,5,5,12,5);path.cubicTo(19,5,15,13,19,17);path.closeSubpath();painter.drawPath(path)
        painter.drawArc(QRectF(10,17,4,4),180*16,180*16)
    elif name=='check':line([(4,12),(10,18),(20,6)])
    elif name=='settings':
        line([(4,7),(10,7)]);line([(15,7),(20,7)]);painter.drawEllipse(QPointF(12.5,7),2.5,2.5)
        line([(4,17),(7,17)]);line([(12,17),(20,17)]);painter.drawEllipse(QPointF(9.5,17),2.5,2.5)
    elif name=='collapse':line([(6,14),(12,8),(18,14)])
    elif name=='fold':line([(8,5),(15,12),(8,19)])
    elif name=='less':line([(5,15),(12,8),(19,15)])
    elif name=='plus':line([(4,12),(20,12)]);line([(12,4),(12,20)])
    painter.end()
    return QIcon(pm)


def color_icon(key):
    swatch=QPixmap(24,24);swatch.setDevicePixelRatio(2);swatch.fill(Qt.transparent)
    painter=QPainter(swatch);painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen);painter.setBrush(QColor(COLORS[key][1]));painter.drawRoundedRect(QRectF(0,0,12,12),4,4)
    painter.end()
    return QIcon(swatch)


def tool(name,title,callback,ink,text=''):
    item=QToolButton()
    item.setIcon(icon(name,ink)); item.setIconSize(QSize(16,16))
    item.setToolTip(title);item.setAccessibleName(title);item.setAutoRaise(True)
    if text:
        item.setText(text);item.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    item.clicked.connect(callback);item.setCursor(Qt.PointingHandCursor)
    return item


def plain_drop(mime):
    if not mime.hasText() or any(url.isLocalFile() for url in mime.urls()):return ''
    return mime.text() if mime.text().strip() else ''


def copy_drop(event):
    event.setDropAction(Qt.CopyAction)
    event.accept()


class Swatch(QToolButton):
    def __init__(self,key,callback):
        super().__init__()
        self.key=key
        self.setFixedSize(25,26);self.setCheckable(True);self.setAutoRaise(True)
        name=COLORS[key][0]
        self.setAccessibleName('筛选'+name);self.setToolTip(name);self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(lambda:callback(key))

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        color=QColor(COLORS[self.key][1]);center=QRectF(self.rect()).center()
        painter.setPen(Qt.NoPen);painter.setBrush(color);painter.drawEllipse(center,6,6)
        if self.isChecked() or self.hasFocus():
            painter.setPen(QPen(self.palette().text().color(),1.5));painter.setBrush(Qt.NoBrush);painter.drawEllipse(center,9,9)


class IdeaEditor(QPlainTextEdit):
    submit=pyqtSignal()
    too_long=pyqtSignal()
    height_changed=pyqtSignal()
    def __init__(self):
        super().__init__()
        self.composing=False
        self.setPlaceholderText('写下此刻的想法…')
        self.setAccessibleName('闪念正文');self.setTabChangesFocus(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.textChanged.connect(self.fit_text)
        self.fit_text()

    def fit_text(self):
        document=self.document()
        block=document.firstBlock()
        lines=0
        while block.isValid() and lines<4:
            document.documentLayout().blockBoundingRect(block)
            lines+=max(1,block.layout().lineCount())
            block=block.next()
        height=self.fontMetrics().lineSpacing()*max(2,min(4,lines))+round(2*document.documentMargin())+6+2*self.frameWidth()
        if self.height()!=height:
            self.setFixedHeight(height)
            self.height_changed.emit()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if event.size().width()!=event.oldSize().width():self.fit_text()

    def fits(self,text,replaced=0):
        size=len(self.toPlainText())-len(self.textCursor().selectedText())-replaced+len(text)
        if size<=MAX_TEXT:return True
        self.too_long.emit()
        return False
    def inputMethodEvent(self,event):
        if event.commitString() and not self.fits(event.commitString(),max(0,event.replacementLength())):
            event.accept();self.composing=False;return
        self.composing=bool(event.preeditString())
        super().inputMethodEvent(event)
    def keyPressEvent(self,event):
        if event.key() in (Qt.Key_Return,Qt.Key_Enter) and event.modifiers() in (Qt.NoModifier,Qt.KeypadModifier) and not self.composing:
            self.submit.emit();event.accept();return
        if event.text() and (event.text().isprintable() or event.key() in (Qt.Key_Return,Qt.Key_Enter)) and not event.modifiers()&Qt.ControlModifier and not self.fits(event.text()):
            event.accept();return
        super().keyPressEvent(event)
    def insertFromMimeData(self,mime):
        if mime.hasText() and self.fits(mime.text()):self.insertPlainText(mime.text())
    def dropEvent(self,event):
        text=plain_drop(event.mimeData())
        if not text or not self.property('allowTextDrop') or not event.possibleActions()&Qt.CopyAction:
            event.ignore();return
        self.setTextCursor(self.cursorForPosition(event.pos()))
        if self.fits(text):self.insertPlainText(text);copy_drop(event)
        else:event.ignore()


class CapsuleDelegate(QStyledItemDelegate):
    def __init__(self,panel):
        super().__init__(panel.list)
        self.panel=panel
    def bubble(self,rect,metrics,text,adorn):
        available=max(1,rect.width()-6)
        width=min(available,max(82,metrics.horizontalAdvance(text)+40+adorn))
        return QRectF(rect.right()-width-2,rect.top()+3,width,max(1,rect.height()-6))
    def paint(self,painter,option,index):
        identity=index.data(Qt.UserRole)
        row=self.panel.rows.get(identity)
        if not row or self.panel.expanded==identity:return
        text=index.data(Qt.DisplayRole);adorn=18 if row['pinned'] or row['due'] else 0
        rect=self.bubble(option.rect,option.fontMetrics,text,adorn)
        fill=self.panel.colors['fills'][row['color']]
        ink=QColor(text_ink(fill))
        painter.save();painter.setRenderHint(QPainter.Antialiasing);painter.setRenderHint(QPainter.TextAntialiasing)
        focus=bool(option.state&QStyle.State_HasFocus)
        outline=QColor(ink)
        pulse=self.panel.pulse_level if identity==self.panel.recent else 0
        outline.setAlphaF(max(pulse,1 if focus else 0))
        painter.setPen(QPen(outline,1.3+pulse) if focus or pulse else Qt.NoPen)
        painter.setBrush(QColor(fill));painter.drawRoundedRect(rect,rect.height()/2,rect.height()/2)
        check=QRectF(rect.left()+11,rect.center().y()-6,12,12)
        painter.setPen(QPen(ink,1.3));painter.setBrush(Qt.NoBrush);painter.drawRoundedRect(check,3,3)
        if row['done']:
            path=QPainterPath(check.topLeft()+QPointF(2.5,6));path.lineTo(check.topLeft()+QPointF(5,9));path.lineTo(check.topLeft()+QPointF(10,3));painter.drawPath(path)
        area=rect.adjusted(30,0,-10-adorn,0)
        painter.setFont(option.font);painter.setPen(ink)
        painter.drawText(area,Qt.AlignVCenter|Qt.AlignLeft,option.fontMetrics.elidedText(text,Qt.ElideRight,max(0,round(area.width()))))
        if adorn:
            symbol=self.panel.row_icon('pin' if row['pinned'] else 'bell',ink.name())
            symbol.paint(painter,QRect(round(rect.right()-24),round(rect.center().y()-7),14,14))
        painter.restore()


class CapsuleList(QListWidget):
    def __init__(self,panel):
        super().__init__()
        self.panel=panel;self.setObjectName('FlashList');self.setAccessibleName('闪念列表')
        self.setDragDropMode(QAbstractItemView.NoDragDrop);self.setAcceptDrops(False);self.viewport().setAcceptDrops(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setResizeMode(QListView.Adjust)
        self.setSpacing(1);self.setMouseTracking(True)
        self.itemActivated.connect(lambda item:panel.expand(item.data(Qt.UserRole)))
    def mouseReleaseEvent(self,event):
        item=self.itemAt(event.pos())
        if item is not None and event.button()==Qt.LeftButton:
            identity=item.data(Qt.UserRole)
            row=self.panel.rows.get(identity)
            if row and self.panel.expanded!=identity:
                rect=self.itemDelegate().bubble(self.visualItemRect(item),self.fontMetrics(),item.text(),18 if row['pinned'] or row['due'] else 0)
                if rect.contains(QPointF(event.pos())):
                    if event.x()<=rect.left()+27 and not row['deleted']:
                        self.panel.service.modify(identity, done=not row['done'])
                    else:self.panel.expand(identity)
                    event.accept();return
        super().mouseReleaseEvent(event)


class ToolGlass(QFrame):
    """Paint glass only under visible controls or the input area."""
    def __init__(self,panel,corner=None):
        super().__init__()
        from capsule_glass import CapsuleGlass
        self.panel=panel
        self.corner=corner
        self.material=CapsuleGlass()

    def hideEvent(self,event):
        self.material.clear()
        super().hideEvent(event)

    def paintEvent(self,event):
        painter=QPainter(self)
        radius=max(0,self.height()/2-.8)
        if self.corner is not None:radius=min(radius,self.corner)
        self.material.paint(painter,self,self.panel,radius)
        if self.corner is not None:
            # A light edit surface preserves contrast on patterned wallpaper. Even clear
            # material needs a nonzero alpha for clicks in a Windows layered text field.
            ink=QColor(self.panel.colors['surface'])
            ink.setAlpha(1 if self.panel.service.cfg['panel_material']=='clear' else 132)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(Qt.NoPen);painter.setBrush(ink)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(1,1,-1,-1),radius,radius)

