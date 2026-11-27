"""Precomposed icon reflections and lightweight, native Dock utility controls."""
import math,datetime
from PyQt5.QtCore import QObject,QTimer,Qt,QRectF,QPointF,QSize,QPoint,QMimeData,QEvent
from PyQt5.QtGui import QPixmap,QPainter,QColor,QLinearGradient,QFont,QPen,QDrag,QPainterPath
from PyQt5.QtWidgets import QDialog,QPushButton,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QApplication,QStackedWidget,QWidget,QFrame,QToolTip

from quick_actions import ACTIONS,DEFAULT_ORDER,GLOBAL_CYCLES,MIME,PAGE_STARTS,QUICK_PAGES,SHELL_ACTIONS,TILE_TINTS,WIDGET_SWITCHES,normalize_order,page_for
from quick_cycles import SHELL_CYCLES, WIDGET_STYLES, next_cycle, shell_cycle_index, widget_style_choices, widget_style_state
from dock_icon_shape import circular_icon
from background_contrast import blend, foreground, wallpaper_color
from compact_clock import ROTATE_SECONDS, clock_width, draw_clock, headers, lines_at

REFLECTION_BUDGET=2*1024*1024


def compose_reflection(source,limit):
    edge=max(1,min(limit,source.width(),source.height()))
    original=source.scaled(edge,edge,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
    gap=max(1,round(edge*.035));height=max(1,round(edge*.28))
    reflection=QPixmap.fromImage(original.toImage().mirrored(False,True)).scaled(edge,height,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
    paint=QPainter(reflection);paint.setCompositionMode(QPainter.CompositionMode_DestinationIn)
    fade=QLinearGradient(0,0,0,height);fade.setColorAt(0,QColor(0,0,0,90));fade.setColorAt(.6,QColor(0,0,0,23));fade.setColorAt(1,QColor(0,0,0,0))
    paint.fillRect(reflection.rect(),fade);paint.end()
    result=QPixmap(edge,edge+gap+height);result.fill(Qt.transparent)
    paint=QPainter(result);paint.drawPixmap(0,0,original);paint.drawPixmap(0,edge+gap,reflection);paint.end()
    return result,(gap+height)/edge


def symbol(p,rect,kind,color):
    p.save();p.translate(rect.x(),rect.y());p.scale(rect.width()/24,rect.height()/24)
    pen=QPen(color,1.6);pen.setCapStyle(Qt.RoundCap);pen.setJoinStyle(Qt.RoundJoin);p.setPen(pen);p.setBrush(Qt.NoBrush)
    if kind=='grid':
        p.setPen(Qt.NoPen);p.setBrush(color)
        for x in (5,12,19):
            for y in (5,12,19):p.drawRoundedRect(QRectF(x-1.5,y-1.5,3,3),.9,.9)
    elif kind=='plus':p.drawLine(12,4,12,20);p.drawLine(4,12,20,12)
    elif kind=='layers':
        for y in (7,12,17):
            p.drawPolyline(QPointF(2,y),QPointF(12,y+5),QPointF(22,y))
        p.drawLine(2,7,12,2);p.drawLine(12,2,22,7)
    elif kind=='pointer_pass':
        p.drawRoundedRect(QRectF(13,3,8,17),2,2)
        p.drawLine(2,12,17,12);p.drawLine(11,7,17,12);p.drawLine(11,17,17,12)
    elif kind=='fade':
        p.drawEllipse(QRectF(3,3,18,18))
        for x,inset in ((12,1),(15,2),(18,4)):
            p.drawLine(x,3+inset,x,21-inset)
    elif kind=='snap_cards':
        p.drawRoundedRect(QRectF(2,5,8,14),2,2);p.drawRoundedRect(QRectF(14,5,8,14),2,2)
        p.drawLine(10,12,14,12)
    elif kind=='card_lock':
        p.drawRoundedRect(QRectF(4,10,16,11),2,2);p.drawArc(QRectF(8,3,8,12),0,180*16)
        p.drawLine(8,9,8,10);p.drawLine(16,9,16,10);p.drawLine(12,14,12,17)
    elif kind=='spectrum':
        for x,h in ((3,5),(7,11),(11,17),(15,12),(19,8)):p.drawLine(x,round(12-h/2),x,round(12+h/2))
    elif kind=='halo':
        p.drawRoundedRect(QRectF(2,6,20,12),6,6)
        p.drawArc(QRectF(5,9,14,6),30*16,126*16)
    elif kind=='apps':
        for x in (4,14):
            for y in (4,14):p.drawRoundedRect(QRectF(x,y,6,6),1.5,1.5)
    elif kind=='palette':
        p.drawEllipse(QRectF(3,3,18,18));p.setPen(Qt.NoPen)
        for x,y in ((8,7),(15,7),(7,13),(16,13)):p.setBrush(color);p.drawEllipse(QPointF(x,y),1.4,1.4)
    elif kind=='size':p.drawRoundedRect(QRectF(3,9,7,10),1,1);p.drawRoundedRect(QRectF(13,4,8,15),1,1)
    elif kind=='position':p.drawRoundedRect(QRectF(2,4,20,15),2,2);p.drawLine(6,16,18,16);p.drawLine(9,22,15,22)
    elif kind=='text_color':
        p.drawLine(5,17,11,4);p.drawLine(11,4,17,17);p.drawLine(8,12,14,12)
        p.drawLine(4,21,20,21);p.setBrush(color);p.drawEllipse(QRectF(18,5,4,4))
    elif kind=='start_menu':
        p.drawRoundedRect(QRectF(3,3,18,18),2,2)
        p.drawLine(12,3,12,21)
        p.drawLine(3,12,21,12)
    elif kind=='bell':
        outline = QPainterPath(QPointF(4,17))
        outline.cubicTo(6,15,6,13,6,10)
        outline.cubicTo(6,6,8.5,4,12,4)
        outline.cubicTo(15.5,4,18,6,18,10)
        outline.cubicTo(18,13,18,15,20,17)
        outline.closeSubpath()
        p.drawPath(outline)
        p.drawArc(QRectF(9,17,6,5),180*16,180*16)
        p.drawLine(12,2,12,4)
    elif kind=='cursor':
        outline = QPainterPath(QPointF(5,3))
        outline.lineTo(20,13)
        outline.lineTo(13,14)
        outline.lineTo(9,21)
        outline.closeSubpath()
        p.drawPath(outline)
    elif kind=='panels':p.drawRoundedRect(QRectF(3,3,8,18),2,2);p.drawRoundedRect(QRectF(14,3,8,8),2,2);p.drawRoundedRect(QRectF(14,14,8,7),2,2)
    elif kind=='magnify':p.drawEllipse(QRectF(3,3,13,13));p.drawLine(14,14,21,21);p.drawLine(6,9,12,9);p.drawLine(9,6,9,12)
    elif kind=='search':p.drawEllipse(QRectF(3,3,13,13));p.drawLine(14,14,21,21)
    elif kind=='undo':
        p.drawArc(5,6,15,14,-45*16,245*16);p.drawLine(4,5,4,12);p.drawLine(4,12,11,12)
    elif kind=='layouts':
        p.drawRoundedRect(QRectF(2,3,20,18),2,2);p.drawLine(2,9,22,9);p.drawLine(10,9,10,21)
    elif kind=='repair':
        p.drawRoundedRect(QRectF(3,3,12,18),2,2);p.drawLine(6,8,11,8);p.drawLine(6,12,10,12)
        p.drawEllipse(QRectF(12,12,7,7));p.drawLine(18,18,22,22)
    elif kind=='monitor':
        for x,y in ((4,13),(10,5),(16,10)):p.drawRoundedRect(QRectF(x,y,3,20-y),1,1)
    elif kind=='flash':
        path=QPainterPath(QPointF(13,2));path.lineTo(5,14);path.lineTo(11,14);path.lineTo(10,22);path.lineTo(19,9);path.lineTo(13,9);path.closeSubpath();p.drawPath(path)
    elif kind=='notes':
        p.drawRoundedRect(QRectF(4,3,16,18),2,2);p.drawLine(8,8,16,8);p.drawLine(8,12,16,12);p.drawLine(8,16,13,16)
    elif kind=='clock':p.drawEllipse(QRectF(3,3,18,18));p.drawLine(12,6,12,12);p.drawLine(12,12,17,14)
    elif kind=='watermark':
        p.drawRoundedRect(QRectF(2,4,20,16),2,2)
        p.translate(12,12);p.rotate(-18);p.drawLine(-4,-4,4,-4);p.drawLine(0,-4,0,5)
    elif kind in ('paw','tray_paw'):
        if kind=='tray_paw':
            p.drawLine(3,21,21,21);p.translate(2,0);p.scale(.84,.84)
        for x,y in ((4,9),(9,5),(15,5),(20,9)):p.drawEllipse(QPointF(x,y),1.6,2.1)
        pad=QPainterPath(QPointF(6,17));pad.cubicTo(6,14,10,10,12,10);pad.cubicTo(15,10,20,16,17,18)
        pad.cubicTo(15,20,13,17,11,18);pad.cubicTo(8,19,6,19,6,17);p.drawPath(pad)
    elif kind=='leaf':
        leaf=QPainterPath(QPointF(5,18));leaf.cubicTo(0,7,13,4,21,3);leaf.cubicTo(20,14,16,21,5,18);p.drawPath(leaf);p.drawLine(3,21,15,9)
    elif kind=='picture':
        p.drawRoundedRect(QRectF(2,4,20,16),2,2);p.drawEllipse(QPointF(8,9),1.4,1.4)
        p.drawLine(3,17,8,13);p.drawLine(8,13,11,15);p.drawLine(11,15,17,9);p.drawLine(17,9,21,13)
    elif kind=='calendar':
        p.drawRoundedRect(QRectF(3,5,18,16),2,2);p.drawLine(3,10,21,10);p.drawLine(8,3,8,7);p.drawLine(16,3,16,7)
        for x in (8,13,18):p.drawPoint(x,14);p.drawPoint(x,18)
    elif kind=='reflection':p.drawRoundedRect(QRectF(7,2,10,9),2,2);p.drawLine(3,14,21,14);p.drawLine(8,18,16,18);p.drawLine(10,21,14,21)
    elif kind=='blur':
        for x in (5,12,19):
            for y in (5,12,19):p.drawEllipse(QPointF(x,y),1.2 if x==5 else 1.8,1.2 if x==5 else 1.8)
    elif kind=='corner':p.drawArc(3,3,18,18,90*16,90*16);p.drawLine(3,12,3,21);p.drawLine(12,3,21,3)
    elif kind=='startup':
        p.drawRoundedRect(QRectF(2,6,19,12),3,3);p.drawLine(23,10,23,14);p.drawLine(8,10,8,14);p.drawLine(12,10,12,14)
    else:p.drawRoundedRect(QRectF(3,4,18,16),2,2);p.drawLine(6,9,18,9);p.drawLine(9,6,9,18)
    p.restore()


class QuickTile(QPushButton):
    def __init__(self,popup,key,title,kind):
        super().__init__(popup);self.popup=popup;self.key=key;self.title=title;self.kind=kind;self.value='';self.active=None
        self.tint=QColor(TILE_TINTS[key])
        self.setObjectName('QuickTile')
        self.setAccessibleName(title)
        self.setMinimumSize(84,82)
        # Tooltips are parented to the hovered button. Keep tile sizing and
        # transparency off QTipLabel, which otherwise becomes a tall black box.
        self.setStyleSheet('QPushButton#QuickTile {min-width:84px;min-height:82px;max-height:82px;padding:0;border:0;background:transparent;}')
        self.setCursor(Qt.PointingHandCursor);self.setAutoDefault(False)
        self.clicked.connect(lambda:popup.activate(key))
        self.drag_start=None;self.dragged=False;self.setAcceptDrops(True)
    def mousePressEvent(self,event):
        self.drag_start=event.pos() if event.button()==Qt.LeftButton else None;self.dragged=False
        super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if self.popup.editing and self.drag_start is not None and event.buttons()&Qt.LeftButton and (event.pos()-self.drag_start).manhattanLength()>=QApplication.startDragDistance():
            self.drag_start=None;self.dragged=True;self.setDown(False)
            drag=QDrag(self);mime=QMimeData();mime.setData(MIME,self.key.encode('ascii'));drag.setMimeData(mime)
            drag.setPixmap(self.grab());drag.setHotSpot(QPoint(self.width()//2,self.height()//2));drag.exec_(Qt.MoveAction);return
        super().mouseMoveEvent(event)
    def mouseReleaseEvent(self,event):
        if self.dragged:self.dragged=False;self.setDown(False);event.accept();return
        super().mouseReleaseEvent(event)
    def dragEnterEvent(self,event):
        if self.popup.valid_drag(event):event.setDropAction(Qt.MoveAction);event.accept()
        else:event.ignore()
    def dragMoveEvent(self,event):self.dragEnterEvent(event)
    def dropEvent(self,event):
        if not self.popup.valid_drag(event):event.ignore();return
        key=bytes(event.mimeData().data(MIME)).decode('ascii')
        if self.popup.move_action(key,self.key):event.setDropAction(Qt.MoveAction);event.accept()
        else:event.ignore()
    def contextMenuEvent(self,event):
        if not self.popup.editing:
            if self.key=='clock':
                runtime=getattr(self.popup.dock.tray,'runtime',None)
                clock=getattr(runtime,'clock',None)
                if clock:
                    self.popup.close()
                    clock.open_progress()
            elif self.key == 'cursor_styles':
                runtime = getattr(self.popup.dock.tray, 'runtime', None)
                if runtime:
                    from settings_catalog import CURSORS
                    from shell_menu import open_settings
                    self.popup.close()
                    open_settings(runtime, CURSORS)
            return
        from ui_style import AlignedMenu
        menu=AlignedMenu(self);order=self.popup.order();page=page_for(order.index(self.key))
        previous=menu.addAction('移到上一页');previous.setEnabled(page>0);previous.triggered.connect(lambda:self.popup.move_to_page(self.key,page-1))
        following=menu.addAction('移到下一页');following.setEnabled(page<self.popup.pages.count()-1);following.triggered.connect(lambda:self.popup.move_to_page(self.key,page+1))
        first=order[PAGE_STARTS[page]];menu.addAction('移到本页开头').triggered.connect(lambda:self.popup.move_action(self.key,first))
        menu.exec_(event.globalPos());menu.deleteLater()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);colors=self.popup.colors()
        rect=QRectF(self.rect()).adjusted(1,1,-1,-1)
        base=(252,253,255) if colors['light'] else (26,31,37)
        amount=.48 if self.active else .17 if self.active is False else .29
        background=QColor(*(round(v) for v in blend(self.tint.getRgb()[:3],base,amount)))
        alpha=188 if self.active else 132 if self.active is False else 159
        background.setAlpha(min(232,alpha+(40 if self.isDown() else 20 if self.underMouse() else 0)))
        outline=QColor(self.tint);outline.setAlpha(195 if self.active or self.hasFocus() else 66)
        p.setPen(QPen(colors['ink'] if self.hasFocus() else outline,1.5 if self.hasFocus() else 1))
        p.setBrush(background);p.drawRoundedRect(rect,8,8)
        title_ink = colors['ink'] if self.isEnabled() else colors['muted']
        accent=self.tint.darker(156) if colors['light'] else self.tint.lighter(166)
        symbol(p,QRectF((self.width()-25)/2,11,25,25),self.kind,accent if self.isEnabled() else title_ink)
        if self.active is not None and not self.popup.editing:
            mark=QRectF(self.width()-18,7,10,10)
            p.setPen(QPen(accent,1.2));p.setBrush(accent if self.active else Qt.NoBrush);p.drawEllipse(mark)
            if self.active:
                p.setPen(QPen(QColor('white' if colors['light'] else '#17212c'),1.3))
                corner=mark.topLeft()
                p.drawLine(corner+QPointF(2,5),corner+QPointF(4.2,7))
                p.drawLine(corner+QPointF(4.2,7),corner+QPointF(8,3))
        font=QFont('Microsoft YaHei UI');font.setPixelSize(12);font.setWeight(QFont.DemiBold);p.setFont(font);p.setPen(title_ink)
        p.drawText(QRectF(3,42,self.width()-6,18),Qt.AlignCenter,self.title)
        font.setPixelSize(10);font.setWeight(QFont.Normal);p.setFont(font);p.setPen(colors['muted'])
        p.drawText(QRectF(3,62,self.width()-6,15),Qt.AlignCenter,self.value)
        if self.popup.editing:
            p.setPen(Qt.NoPen);p.setBrush(colors['muted'])
            for x in (self.width()-12,self.width()-8):
                for y in (8,12,16):p.drawEllipse(QPointF(x,y),.8,.8)


class PageTurnButton(QPushButton):
    def __init__(self,popup,direction):
        super().__init__(popup);self.popup=popup;self.direction=direction
        self.setObjectName('QuickNav');self.setFixedSize(26,24);self.setAcceptDrops(True)
        self.setAccessibleName('上一页' if direction < 0 else '下一页')
        self.clicked.connect(lambda:popup.set_page(popup.pages.currentIndex()+direction))
        self.hover_timer=QTimer(self);self.hover_timer.setSingleShot(True);self.hover_timer.setInterval(380)
        self.hover_timer.timeout.connect(lambda:popup.set_page(popup.pages.currentIndex()+direction))
    def dragEnterEvent(self,event):
        if self.popup.valid_drag(event):event.acceptProposedAction();self.hover_timer.start()
        else:event.ignore()
    def dragLeaveEvent(self,event):self.hover_timer.stop();event.accept()
    def dropEvent(self,event):
        self.hover_timer.stop()
        if self.popup.valid_drag(event):
            key=event.source().key;page=max(0,min(self.popup.pages.currentIndex()+self.direction,self.popup.pages.count()-1))
            if self.popup.move_to_page(key,page):event.setDropAction(Qt.MoveAction);event.accept();return
        event.ignore()


class DockQuickSettings(QDialog):
    def __init__(self,extras):
        super().__init__(extras.dock,Qt.Popup|Qt.FramelessWindowHint|Qt.NoDropShadowWindowHint)
        self.extras=extras;self.dock=extras.dock;self.setObjectName('DockQuickSettings');self.setWindowTitle('Dock 快捷设置')
        self.setProperty('ownsPopupStyle',True)
        self.setAttribute(Qt.WA_TranslucentBackground);self.setAttribute(Qt.WA_NoMouseReplay);self.setFixedSize(320,378)
        self.editing=False;self._wheel_delta=0;self._bound_taskbar=None
        self.backdrop=None;self._backdrop_key=None;self.spec_alpha=0.0
        self._light_ink=None;self._control_palette=None
        body=QVBoxLayout(self);body.setContentsMargins(16,12,16,12);body.setSpacing(9)
        header=QHBoxLayout();self.title=QLabel('快捷设置');self.title.setObjectName('QuickTitle')
        header.addWidget(self.title,0,Qt.AlignVCenter);header.addStretch()
        self.reset_button=QPushButton('重置');self.reset_button.setFixedSize(38,26);self.reset_button.clicked.connect(self.reset_order);header.addWidget(self.reset_button);self.reset_button.hide()
        self.edit_button=QPushButton('排序');self.edit_button.setFixedSize(38,26);self.edit_button.setCheckable(True);self.edit_button.clicked.connect(self.toggle_edit);header.addWidget(self.edit_button)
        self.edit_button.setToolTip('拖动按钮可交换位置。拖到翻页按钮或右键可跨页移动。')
        self.close_button=QPushButton(self);self.close_button.setObjectName('QuickClose');self.close_button.setAccessibleName('关闭快捷设置')
        self.close_button.setFixedSize(26,26);self.close_button.clicked.connect(self.close);header.addWidget(self.close_button);body.addLayout(header)
        self.pages=QStackedWidget();self.pages.setObjectName('QuickPages');self.pages.setFrameShape(QFrame.NoFrame);self.pages.setAutoFillBackground(False)
        self.pages.setStyleSheet('QStackedWidget#QuickPages,QWidget#QuickPage {background:transparent;border:0;}')
        self.page_grids=[]
        for _ in QUICK_PAGES:
            page=QWidget();page.setObjectName('QuickPage');grid=QGridLayout(page);grid.setContentsMargins(0,0,0,0);grid.setSpacing(7)
            for row in range(3):grid.setRowStretch(row,1)
            for column in range(3):grid.setColumnStretch(column,1)
            self.pages.addWidget(page);self.page_grids.append(grid)
        self.tiles={key:QuickTile(self,key,title,kind) for key,title,kind in ACTIONS}
        body.addWidget(self.pages,1)
        footer=QHBoxLayout()
        self.status=QLabel('滚轮翻页');self.status.setMinimumWidth(1)
        footer.addWidget(self.status,0,Qt.AlignVCenter);footer.addStretch()
        self.status_timer=QTimer(self);self.status_timer.setSingleShot(True)
        self.status_timer.timeout.connect(self.clear_feedback)
        self.prev_button=PageTurnButton(self,-1);self.next_button=PageTurnButton(self,1);self.page_label=QLabel();self.page_label.setAlignment(Qt.AlignCenter);self.page_label.setObjectName('QuickCounter')
        footer.addWidget(self.prev_button);footer.addWidget(self.page_label,0,Qt.AlignVCenter);footer.addWidget(self.next_button);body.addLayout(footer)
        for label in (self.title,self.page_label,self.status):
            label.setProperty('quickCaption',True)
        for button in (self.reset_button,self.edit_button,self.close_button,self.prev_button,self.next_button):
            button.setProperty('quickControl',True)
        self.rebuild_pages()
        for child in self.findChildren(QWidget):child.installEventFilter(self)
        from idle_resources import watch
        watch(self)

    def release_idle_resources(self):
        if self.isVisible():return False
        if self.extras.popup is self:self.extras.popup=None
        self.deleteLater()
        return True
    def eventFilter(self,watched,event):
        if event.type()==QEvent.Wheel:self.wheelEvent(event);return True
        if (watched is self.status and event.type()==QEvent.ToolTip and not watched.toolTip()
                and watched.sizeHint().width()>watched.width()):
            QToolTip.showText(event.globalPos(),watched.text(),watched)
            return True
        return super().eventFilter(watched,event)
    def show_feedback(self,message,detail=''):
        self.status.setText(message)
        self.status.setToolTip(detail)
        self.status_timer.start(5000)
    def clear_feedback(self):
        self.status_timer.stop()
        self.update_page_caption()
    def order(self):return normalize_order(self.dock.cfg.get('dock_quick_order'))
    def rebuild_pages(self):
        current=self.pages.currentIndex()
        for grid in self.page_grids:
            while grid.count():grid.takeAt(0)
        for index,key in enumerate(self.order()):
            page=page_for(index)
            row,column=divmod(index-PAGE_STARTS[page],3)
            tile=self.tiles[key];tile.hide();self.page_grids[page].addWidget(tile,row,column);tile.show()
        self._shown_order=tuple(self.order())
        self.set_page(max(0,current))
    def set_page(self,page):
        page=max(0,min(page,self.pages.count()-1));self.pages.setCurrentIndex(page)
        self.prev_button.setEnabled(page>0);self.next_button.setEnabled(page<self.pages.count()-1)
        self.page_label.setText(str(page+1)+' / '+str(self.pages.count()))
        if not self.status_timer.isActive():self.update_page_caption()
    def update_page_caption(self):
        page=self.pages.currentIndex()
        if page<0:return
        title,group=QUICK_PAGES[page]
        start=PAGE_STARTS[page]
        keys=self._shown_order[start:start+len(group)]
        self.status.setText(title if set(keys)==set(group) else '自定义排序')
        self.status.setToolTip('')
        self.page_label.setToolTip('滚轮或箭头翻页')
    def wheelEvent(self,event):
        delta=event.angleDelta().y() or event.pixelDelta().y()*3
        if not delta:event.ignore();return
        if self._wheel_delta*delta<0:self._wheel_delta=0
        self._wheel_delta+=delta
        if abs(self._wheel_delta)>=120:
            self.set_page(self.pages.currentIndex()+(-1 if self._wheel_delta>0 else 1));self._wheel_delta=0
        event.accept()
    def toggle_edit(self):
        self.editing=not self.editing;self.edit_button.setText('完成' if self.editing else '排序');self.reset_button.setVisible(self.editing)
        self.edit_button.setChecked(self.editing)
        self.clear_feedback()
        for tile in self.tiles.values():tile.setCursor(Qt.OpenHandCursor if self.editing else Qt.PointingHandCursor)
        self.refresh()
    def valid_drag(self,event):
        source=event.source()
        return bool(self.editing and isinstance(source,QuickTile) and source.popup is self and event.mimeData().hasFormat(MIME) and bytes(event.mimeData().data(MIME))==source.key.encode('ascii'))
    def save_order(self,order):
        import sys
        from settings_effects import save_changes
        if not save_changes(self.dock.tray,sys.modules[self.dock.__class__.__module__],{'dock_quick_order':order}):self.show_feedback('顺序保存失败，原顺序未改变。');return False
        self.rebuild_pages();return True
    def move_action(self,source,target):
        order=self.order()
        if source not in order or target not in order or source==target:return False
        left,right=order.index(source),order.index(target);order[left],order[right]=order[right],order[left]
        return self.save_order(order)
    def move_to_page(self,key,page):
        if key not in self.tiles or page<0 or page>=self.pages.count():return False
        order=self.order();order.remove(key);order.insert(PAGE_STARTS[page],key)
        if not self.save_order(order):return False
        self.set_page(page);return True
    def reset_order(self):return self.save_order(list(DEFAULT_ORDER))
    def colors(self):
        light=self.dock.is_light() if self._light_ink is None else not self._light_ink
        return {'light':light,'ink':QColor('#152831' if light else '#f6f9fb'),'muted':QColor('#344650' if light else '#d7e0e6')}

    @property
    def cfg(self):
        return self.dock.cfg

    def refresh_surface(self):
        from glass_capture import backdrop_key, capture_behind, smooth_backdrop
        from liquid_glass import dock_tint_layers, material_alpha
        cfg=self.cfg
        colors=self.dock.theme_colors()
        material=cfg.get('dock_material','liquid')
        glass=cfg['glass'] and not cfg.get('clear_background') and material not in ('clear','solid')
        radius=self.dock.blur_divisor()
        key=backdrop_key(self,glass,radius) if not self.dock.preview else None
        if not glass:
            self.backdrop=None
        elif key is not None and (key!=self._backdrop_key or self.backdrop is None):
            sample=capture_behind(self)
            self.backdrop=smooth_backdrop(sample,radius) if sample is not None and not sample.isNull() else None
        self._backdrop_key=key
        wallpaper=wallpaper_color(self,QRectF(self.rect())) if key is not None else None
        tint,opacity=dock_tint_layers(colors,cfg.get('transparency',40))
        alpha=0 if cfg.get('clear_background') else material_alpha(tint,material)*opacity/255
        self._light_ink=foreground(colors['tint'].getRgb()[:3],wallpaper,alpha)=='#ffffff' if wallpaper is not None else not self.dock.is_light()
        self.style_controls(colors['tint'])
        self.update()

    def style_controls(self,tint):
        colors=self.colors()
        key=(colors['light'],tint.rgb())
        if key==self._control_palette:
            return
        self._control_palette=key
        light=colors['light']
        ink=colors['ink']
        from flash_view import icon
        for button, glyph in ((self.close_button,'close'),(self.prev_button,'back'),(self.next_button,'fold')):
            button.setIcon(icon(glyph,ink,18))
            button.setIconSize(QSize(18,18))
        base=blend(tint.getRgb()[:3],(231,238,244) if light else (23,31,44),.18)
        def rgba(rgb,alpha):
            r,g,b=map(round,rgb)
            return f'rgba({r},{g},{b},{alpha})'
        # Both glyph and fill belong to the popup. The desktop can change from
        # light to dark between two controls on the same transparent window.
        ink_rgb=ink.getRgb()[:3]
        hover=blend(ink_rgb,base,.10)
        pressed=blend(ink_rgb,base,.19)
        active=blend(tint.getRgb()[:3],(145,183,211) if light else (42,83,113),.22)
        control='QPushButton[quickControl="true"]'
        caption='QLabel[quickCaption="true"]'
        self.setStyleSheet(f"""
            {control} {{color:{ink.name()}; background:{rgba(base,196)}; border:1px solid {rgba(ink_rgb,90)};
                        border-radius:6px; font-size:12px; min-height:0; padding:0;}}
            {control}:hover {{background:{rgba(hover,220)}; border-color:{rgba(ink_rgb,162)};}}
            {control}:checked {{background:{rgba(active,222)}; border-color:{rgba(ink_rgb,190)};}}
            {control}:checked:hover {{background:{rgba(active,244)};}}
            {control}:pressed, {control}:checked:pressed {{background:{rgba(pressed,238)};}}
            {control}:focus, {control}[keyboardFocus="true"] {{border-color:{ink.name()};}}
            {control}:disabled {{color:{rgba(ink_rgb,156)}; background:{rgba(base,167)}; border-color:{rgba(ink_rgb,47)};}}
            {caption} {{color:{ink.name()}; background:{rgba(base,174)}; border-radius:4px;
                        padding:1px 5px; font-size:10px;}}
            QLabel#QuickTitle {{font-size:15px; font-weight:600;}}
            QLabel#QuickCounter {{font-size:11px;}}
        """)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHints(QPainter.Antialiasing|QPainter.SmoothPixmapTransform)
        rect=QRectF(self.rect()).adjusted(1,1,-1,-1)
        path=QPainterPath();path.addRoundedRect(rect,16,16)
        p.fillPath(path,QColor(0,0,0,2))
        self.dock.paint_dock_surface(self,p,[path],rect,self.dock.theme_colors())
    def refresh(self):
        if tuple(self.order())!=getattr(self,'_shown_order',None):self.rebuild_pages()
        from appearance_profiles import MODES as PROFILE_MODES, selected_mode
        cfg=self.dock.cfg;runtime=getattr(self.dock.tray,'runtime',None)
        current=selected_mode(cfg)
        preset=next(name for name,mode in PROFILE_MODES if mode==current)
        values={'settings':'完整选项','add':'应用、文件、文件夹','manage':'批量添加 / 移除','appearance':preset,
                'size':str(cfg['icon_size'])+' 像素','position':{'bottom':'底部','top':'顶部','custom':'自定义'}.get(cfg['position'],'底部'),
                'panels':'已开启' if cfg['panel_enabled'] else '已关闭','magnify':'已开启' if cfg['magnify'] else '已关闭',
                'notes':'已开启' if cfg['notes_enabled'] and cfg['notes_visible'] else '已关闭',
                'clock':'已开启' if cfg['clock_enabled'] else '已关闭','calendar':'已开启' if cfg['calendar_enabled'] else '已关闭',
                'watermark':'已开启' if cfg['watermark_enabled'] else '已关闭',
                'reflections':'已开启' if cfg['dock_reflections'] else '已关闭','dock_time':'已开启' if cfg['dock_clock'] else '已关闭',
                'color_mode':{'auto':'跟随系统','light':'浅色','dark':'深色'}.get(cfg['theme'],'跟随系统'),
                'blur':'已开启' if cfg['glass'] else '已关闭','panel_auto_hide':'已开启' if cfg['panel_auto_hide'] else '已关闭',
                'corners':'已开启' if cfg['screen_corners'] else '已关闭',
                'search':'应用 / 文件 / 便签','undo':'暂无可撤销',
                'layouts':'保存 / 切换布局','references':'检查 / 重新定位'}
        values['taskbar_monitor']='已开启' if cfg['resource_taskbar'] else '已关闭'
        for key,(_,_,field,_,tip) in WIDGET_SWITCHES.items():
            enabled=cfg[field]
            if key=='almanac_alert':
                from resource_options import almanac_categories
                enabled=bool(almanac_categories(cfg))
            values[key]='已开启' if enabled else '已关闭'
            self.tiles[key].setToolTip(tip)
            self.tiles[key].setAccessibleDescription(values[key])
        for key,(_,_,field,modes) in GLOBAL_CYCLES.items():
            values[key]=dict(modes)[cfg[field]]
            self.tiles[key].setToolTip(' → '.join(label for _,label in modes[1:]+modes[:1])+'。自定义使用各组件自己的设置。')
        for key in WIDGET_STYLES:
            labels = dict(widget_style_choices(key), custom='自定义', off='已关闭')
            mode, _ = widget_style_state(cfg, key)
            values[key] = labels[mode]
            self.tiles[key].setToolTip(' → '.join(labels.values()) + '。自定义恢复你保存的样式。')
        self.tiles['clock'].setToolTip('左键开关时钟，右键设置时光进度与倒计时')
        values['resources']='已开启' if cfg['resource_enabled'] else '已关闭'
        self.tiles['resources'].setToolTip('切换桌面灵动胶囊')
        values['flash']='已开启' if cfg['flash_enabled'] else '已关闭'
        self.tiles['flash'].setToolTip('切换桌面闪念胶囊')
        productivity=getattr(runtime,'productivity',None)
        if productivity:
            history=getattr(productivity,'history',None);steps=len(getattr(history,'entries',[]))
            values['undo']='可撤销 · %d 步'%steps if steps else '暂无可撤销'
            self.tiles['undo'].setToolTip(getattr(history,'message','撤销最近的引用和布局整理，原文件保持不变。'))
        else:
            for key in ('search','undo','layouts','references'):values[key]='暂不可用'
        self.tiles['search'].setToolTip('搜索已添加的应用、卡片文件、便签、闪念和设置，不扫描磁盘。')
        self.tiles['layouts'].setToolTip('保存当前桌面布局，或切换到已保存的方案。')
        self.tiles['references'].setToolTip('手动检查失效入口、重新定位或移除引用；原文件保持不变。')
        from taskbar_appearance import MODES
        values['taskbar'] = dict((key, title) for title, key in MODES).get(cfg.get('taskbar_mode'), '跟随系统')
        values['taskbar_text'] = {'system':'跟随系统','light':'浅色文字 · 白字','dark':'深色文字 · 黑字'}.get(cfg.get('taskbar_text_mode'), '跟随系统')
        if cfg.get('taskbar_text_auto'):values['taskbar_text'] = '随壁纸自动配色'
        self.tiles['taskbar_text'].setToolTip('点击切换跟随系统、白字、黑字或随壁纸自动配色。')
        shell = getattr(runtime, 'shell_appearance', None)
        shell_supported = shell is not None and shell.supported
        for key in SHELL_ACTIONS:
            tile = self.tiles[key]
            tile.setEnabled(shell_supported or self.editing)
            if shell_supported:
                choices = SHELL_CYCLES[key]
                selected = shell_cycle_index(cfg, key)
                values[key] = choices[selected][0] if selected is not None else '跟随系统'
                labels = [label for label, _ in choices]
                tile.setToolTip('点击循环切换：' + ' → '.join(labels + labels[:1]))
            else:
                values[key] = '仅 Windows 11' if shell is not None else '暂不可用'
                tile.setToolTip('系统面板美化需要 Windows 11。' if shell is not None else '')
            tile.setAccessibleDescription(values[key])
        cursors = getattr(runtime, 'cursor_styles', None)
        cursor_tile = self.tiles['cursor_styles']
        cursor_styles = cursors.styles() if cursors is not None else []
        cursor_tile.setEnabled(bool(cursor_styles and cursors.system.enabled) or self.editing)
        cursor_tile.setToolTip('点击循环切换鼠标方案，最后恢复系统默认。右键打开设置。')
        try:
            _, cursor_title = cursors.current(cursor_styles) if cursors is not None else (None, '系统默认')
        except OSError:
            cursor_title = '读取失败'
        values['cursor_styles'] = cursor_title
        cursor_tile.setAccessibleDescription(cursor_title)
        taskbar = getattr(runtime, 'taskbar', None)
        if taskbar is not self._bound_taskbar:
            old=getattr(self._bound_taskbar,'changed',None)
            if old is not None:
                try:old.disconnect(self.taskbar_status_changed)
                except (TypeError,RuntimeError):pass
            self._bound_taskbar=taskbar
            changed=getattr(taskbar,'changed',None)
            if changed is not None:changed.connect(self.taskbar_status_changed)
        supported = taskbar is not None and taskbar.backend is not None
        if not supported:
            if getattr(taskbar, 'install_process', None) is not None:
                values['taskbar'] = '正在安装…'
            elif getattr(taskbar, 'payload', None):
                values['taskbar'] = '首次点击启用'
            else:
                values['taskbar'] = '组件未就绪'
        self.tiles['taskbar'].setToolTip(
            '点击循环切换任务栏效果，颜色与模糊强度沿用主设置。' if supported
            else getattr(taskbar, 'status', '任务栏组件未就绪'))
        taskbar_error=getattr(taskbar,'error','')
        if taskbar_error:
            values['taskbar']='应用失败';self.tiles['taskbar'].setToolTip(str(taskbar_error))
        elif supported and getattr(taskbar,'_pending_effect',None) is not None:
            values['taskbar']='正在应用…'
        if cfg['icon_size'] not in (32,42,54,64):values['size']='自定义 · '+str(cfg['icon_size'])
        if cfg['position']=='custom':values['position']='自定义 · '+str(cfg['custom_bottom'])
        self.tiles['appearance'].setToolTip('一起切换 Dock、桌面卡片、便签、时钟、日历和闪念胶囊的主题，循环后恢复各自的自定义外观。')
        for key in ('size','position'):self.tiles[key].setToolTip('点击循环切换，循环一轮可回到已保存的自定义值。')
        for key,tile in self.tiles.items():
            tile.value=values[key]
            tile.active={'已开启':True,'已关闭':False}.get(tile.value)
            description=tile.value
            if key in WIDGET_STYLES:
                tile.active = cfg[WIDGET_STYLES[key][0]]
            elif key == 'idle_fade':
                tile.active = {'on': True, 'off': False}.get(cfg['desktop_idle_fade_mode'])
            if key in SHELL_ACTIONS and shell_supported:
                tile.active=cfg[key+'_enabled']
                description=('已开启' if tile.active else '已关闭')+' · '+tile.value
            tile.setAccessibleDescription(description)
            tile.update()
        if self.isVisible():self.refresh_surface()
    def showEvent(self, event):
        super().showEvent(event)
        self.clear_feedback()
        self.refresh_surface()
        taskbar = self._bound_taskbar
        if hasattr(taskbar, 'reconcile_status'):
            taskbar.reconcile_status()

    def taskbar_status_changed(self,message):
        self.refresh()
        error=getattr(self._bound_taskbar,'error','')
        self.show_feedback('任务栏效果应用失败，请查看提示。' if error else str(message),str(error) if error else '')

    def moveEvent(self,event):
        super().moveEvent(event)
        if self.isVisible():self.refresh_surface()

    def reanchor(self):
        from PyQt5.QtCore import QPoint
        rect=self.extras.rects().get('quick',self.dock.bar_rect_f());anchor=self.dock.mapToGlobal(rect.center().toPoint())
        screen=QApplication.screenAt(anchor) or QApplication.primaryScreen();area=screen.availableGeometry()
        y=self.dock.mapToGlobal(self.dock.bar_rect_f().topLeft().toPoint()).y()-self.height()-10
        if y<area.top():y=self.dock.mapToGlobal(self.dock.bar_rect_f().bottomLeft().toPoint()).y()+10
        self.move(max(area.left()+6,min(anchor.x()-self.width()//2,area.right()-self.width()-5)),max(area.top()+6,min(y,area.bottom()-self.height()-5)))
    def activate(self,key):
        if self.editing:return
        tray=self.dock.tray;runtime=getattr(tray,'runtime',None)
        if not tray:return
        self.clear_feedback()
        if key == 'cursor_styles':
            from cursor_styles import PACK_ERRORS
            cursors = getattr(runtime, 'cursor_styles', None)
            if cursors is not None and cursors.system.enabled:
                try:
                    title = cursors.cycle()
                except PACK_ERRORS as error:
                    self.show_feedback('鼠标样式应用失败',str(error))
                else:
                    self.refresh()
                    self.show_feedback('已应用 · ' + title)
            return
        if key=='taskbar_monitor':
            if runtime:runtime.resources.set_options(resource_taskbar=not runtime.dock.cfg['resource_taskbar'])
            self.refresh();return
        if key=='resources':
            if runtime:
                runtime.resources.set_options(resource_enabled=not runtime.dock.cfg['resource_enabled'])
            self.refresh()
            return
        if key=='flash':
            if runtime and runtime.flash.set_enabled(not runtime.dock.cfg['flash_enabled']):
                self.refresh()
            else:
                self.show_feedback('闪念胶囊设置保存失败。')
            return
        if key in ('search','undo','layouts','references'):
            service=getattr(runtime,'productivity',None)
            if service is None or getattr(service,'closed',False):
                self.show_feedback('整理工具暂不可用，请重新打开设置。');return
            if key=='undo':
                service.undo();self.refresh();self.reanchor()
                self.show_feedback(service.message,service.message);return
            method={'search':'open_search','layouts':'open_layouts','references':'open_references'}[key]
            self.close();getattr(service,method)();return
        if key in ('settings','add','manage'):
            self.close()
            if key=='settings':(runtime.show_settings if runtime else tray.show_settings)()
            elif key=='add':tray.add_icons()
            elif hasattr(tray,'importer'):tray.importer.show()
            return
        cfg=self.dock.cfg;changes={}
        if key in WIDGET_STYLES or key in ('appearance','size','position'):
            notes = getattr(runtime, 'notes', None)
            if key == 'appearance' and notes and not notes.flush():
                self.show_feedback('便签保存失败，外观切换已取消。');return
            changes=next_cycle(cfg,key)
        elif key in GLOBAL_CYCLES:
            _,_,field,modes=GLOBAL_CYCLES[key]
            choices=[value for value,_ in modes]
            changes={field:choices[(choices.index(cfg[field])+1)%len(choices)]}
        elif key in WIDGET_SWITCHES:
            field=WIDGET_SWITCHES[key][2]
            changes={field:not cfg[field]}
            if key=='almanac_alert':
                from resource_options import ALMANAC_CATEGORIES, almanac_categories
                changes[field]=not almanac_categories(cfg)
                if changes[field] and not any(cfg['resource_almanac_'+k] for k in ALMANAC_CATEGORIES):
                    changes.update({'resource_almanac_'+k:True for k in ALMANAC_CATEGORIES})
        elif key=='panels':changes={'panel_enabled':not cfg['panel_enabled'],'panels_visible':True}
        elif key=='magnify':changes={'magnify':not cfg['magnify']}
        elif key=='notes':changes={'notes_enabled':not (cfg['notes_enabled'] and cfg['notes_visible']),'notes_visible':True}
        elif key=='clock':changes={'clock_enabled':not cfg['clock_enabled']}
        elif key=='watermark':changes={'watermark_enabled':not cfg['watermark_enabled']}
        elif key=='calendar':changes={'calendar_enabled':not cfg['calendar_enabled']}
        elif key=='reflections':changes={'dock_reflections':not cfg['dock_reflections']}
        elif key=='dock_time':changes={'dock_clock':not cfg['dock_clock']}
        elif key=='color_mode':
            modes=('auto','light','dark');changes={'theme':modes[(modes.index(cfg['theme'])+1)%3]}
        elif key=='blur':changes={'glass':not cfg['glass']}
        elif key=='panel_auto_hide':changes={'panel_auto_hide':not cfg['panel_auto_hide']}
        elif key in SHELL_ACTIONS:
            shell = getattr(runtime, 'shell_appearance', None)
            if shell is None or not shell.supported:
                return
            changes = next_cycle(cfg, key)
        elif key=='taskbar_text':
            from taskbar_text import MODES
            modes = [value for title, value in MODES] + ['auto']
            current = 'auto' if cfg.get('taskbar_text_auto') else cfg.get('taskbar_text_mode', 'system')
            index = modes.index(current) if current in modes else 0
            selected = modes[(index+1) % len(modes)]
            changes = {'taskbar_text_auto': True} if selected == 'auto' else {'taskbar_text_mode': selected, 'taskbar_text_auto': False}
        elif key=='taskbar':
            taskbar = getattr(runtime, 'taskbar', None)
            if taskbar is None or taskbar.backend is None:
                self.enable_taskbar_component(tray, taskbar)
                return
            from taskbar_appearance import MODES
            modes = [value for title, value in MODES]
            current = cfg.get('taskbar_mode', 'system')
            index = modes.index(current) if current in modes else 0
            changes = {'taskbar_mode': modes[(index+1) % len(modes)]}
        elif key=='corners':changes={'screen_corners':not cfg['screen_corners']}
        if changes:
            from settings_effects import save_changes
            import sys
            if not save_changes(tray,sys.modules[self.dock.__class__.__module__],changes):self.show_feedback('保存失败，未应用更改。');return
        if key=='notes' and changes.get('notes_enabled') and runtime:
            notes=getattr(runtime,'notes',None)
            if notes and not notes.rows() and notes.new() is None:self.show_feedback('便签已启用，但新建失败，请在便签管理中重试。')
        self.refresh();self.reanchor()
        if key in SHELL_ACTIONS:
            self.show_feedback(f'{self.tiles[key].title}样式已保存。')
        if key=='taskbar':
            taskbar=getattr(runtime,'taskbar',None)
            self.taskbar_status_changed(getattr(taskbar,'status','任务栏效果配置已保存。'))
        if key=='taskbar_text':
            error = getattr(getattr(getattr(runtime,'taskbar',None),'text',None),'error','')
            self.show_feedback('任务栏文字应用失败，请查看提示。' if error else '文字颜色已保存 · 联动 Windows 明暗模式',str(error) if error else '')


    def enable_taskbar_component(self, tray, taskbar):
        if not getattr(taskbar, 'payload', None):
            self.show_feedback(getattr(taskbar, 'status', '任务栏组件未就绪。'))
            return
        if taskbar.install_process is not None:
            return

        def installed(success, message):
            import sys
            from PyQt5 import sip
            from settings_effects import save_changes

            if success and tray.cfg.get('taskbar_mode', 'system') == 'system':
                api = sys.modules[tray.dock.__class__.__module__]
                if not save_changes(tray, api, {'taskbar_mode': 'clear'}):
                    message = '组件已安装，效果保存失败。可再次点击启用。'
                else:
                    error=getattr(taskbar,'error','')
                    message = '组件已安装，但效果应用失败：'+str(error) if error else getattr(taskbar,'status','组件已启动，已切换到全透明。')
            if not sip.isdeleted(self):
                self.refresh()
                self.show_feedback(message)

        if taskbar.install_offline(installed):
            self.refresh()
            self.show_feedback('正在离线安装任务栏组件…')


class DockExtras(QObject):
    def __init__(self,dock):
        super().__init__(dock);self.dock=dock;self.popup=None;self.pressed=None;self.hover=None
        self.clock=QTimer(self);self.clock.setSingleShot(True);self.clock.timeout.connect(self.minute)
        self.clock_day = None
        self.clock_ink = None
        self.clock_sample = QTimer(self)
        self.clock_sample.setSingleShot(True)
        self.clock_sample.timeout.connect(self.refresh_clock_ink)
        dock.geo_timer.timeout.connect(self.refresh_clock_ink)
    def reflection_room(self):return max(2,round(self.dock.icon_size*.32)) if self.dock.cfg.get('dock_reflections',True) and self.dock.items else 0
    def bottom_space(self):
        return max(1,round((self.dock.pad_y+self.reflection_room())/2)) if self.reflection_room() else self.dock.pad_y
    def prepare(self,items):
        icons=[it for it in items if not it.get('sep') and it.get('pixmap') is not None]
        limit=min(128,max(24,int(math.sqrt(REFLECTION_BUDGET/max(1,len(icons))/5.6))))
        circle = self.dock.cfg.get('dock_icon_shape') == 'circle'
        edge = max(48, min(384, self.dock.icon_size * 2))
        for item in icons:
            source = item['pixmap']
            shape_key = (source.cacheKey(), edge) if circle else None
            if item.get('_circle_key') != shape_key:
                item.pop('_scaled', None)
                if circle:
                    item['_circle_icon'] = circular_icon(source, edge)
                    item['_circle_key'] = shape_key
                else:
                    item.pop('_circle_icon', None)
                    item.pop('_circle_key', None)
            source = item.get('_circle_icon', source)
            key = (source.cacheKey(), limit)
            if not self.dock.cfg.get('dock_reflections',True):item.pop('_reflected',None);item.pop('_reflection_key',None);continue
            if source.isNull():continue
            if item.get('_reflection_key')!=key:
                item['_reflected'],item['_reflection_ratio']=compose_reflection(source,limit);item['_reflection_key']=key
    def clock_content(self, now):
        cfg = self.dock.cfg
        formats = ('%m/%d', '%H:%M:%S' if cfg['dock_clock_seconds'] else '%H:%M')
        return headers(cfg,'dock_clock_',formats,now.date()), formats[1]

    def utility_sizes(self):
        d = self.dock
        side = max(27,min(48,round(d.icon_size*.88)))
        sizes = []
        if d.cfg.get('dock_clock',True):
            upper, lower = self.clock_content(datetime.datetime.now())
            sizes.append(('clock',clock_width(upper,lower,side,True),4))
        gap = max(7,round(d.icon_size*.22))
        for key, option in (('quick','dock_quick_settings'),('add','dock_add_button')):
            if d.cfg.get(option,True):
                sizes.append((key,side,4 if sizes and sizes[-1][0]=='clock' else gap))
        return side, sizes

    def width(self):
        return sum(width+gap for _,width,gap in self.utility_sizes()[1])

    def rects(self):
        d=self.dock;bar=d.bar_rect_f();side,sizes=self.utility_sizes()
        x=bar.right()-d.pad_x-sum(width+gap for _,width,gap in sizes)
        cy=bar.top()+d.pad_y+d.icon_size/2;out={}
        for key,width,gap in sizes:
            x+=gap;out[key]=QRectF(x,cy-side/2,width,side);x+=width
        return out
    def hit(self,pos):return next((key for key,rect in self.rects().items() if key!='clock' and rect.contains(QPointF(pos))),None)
    def move(self,pos):
        hover=self.hit(pos)
        if hover!=self.hover:self.hover=hover;self.dock.update()
        return hover
    def paint(self,p,colors):
        d=self.dock;now=datetime.datetime.now();ink=colors['fg'];rects=self.rects()
        for key,rect in rects.items():
            if key=='clock':
                ink = self.clock_ink or QColor(foreground(colors['tint'].getRgb()[:3]))
                caption = QColor(ink)
                caption.setAlpha(226)
                upper, lower = self.clock_content(now)
                draw_clock(p,rect,lines_at(now,upper,lower),caption,ink,dock=True)
            else:
                p.save();tint=QColor(255,255,255,85 if colors['light'] else 28);p.setPen(QPen(QColor(128,150,175,25),1));p.setBrush(tint)
                if self.hover==key:p.setBrush(QColor(255,255,255,145 if colors['light'] else 55))
                p.drawRoundedRect(rect,rect.height()*.27,rect.height()*.27)
                size=rect.height()*.60;symbol(p,QRectF(rect.center().x()-size/2,rect.center().y()-size/2,size,size),'grid' if key=='quick' else 'plus',ink);p.restore()
    def activate(self,key):
        if not self.dock.tray:return
        if key=='add':self.dock.tray.add_icons()
        elif key=='quick':
            if self.popup is None:self.popup=DockQuickSettings(self)
            if self.popup.isVisible():self.popup.close();return
            self.popup.refresh();self.popup.reanchor();self.popup.show()
    def refresh_clock_ink(self):
        if self.dock.preview or not self.dock.isVisible() or not self.dock.cfg.get('dock_clock', True):
            return
        rect = self.rects()['clock']
        try:
            surface = wallpaper_color(self.dock, rect)
        except (OSError, ValueError, RuntimeError):
            return
        if surface is not None:
            ink = QColor(foreground(surface))
            if ink != self.clock_ink:
                self.clock_ink = ink
                self.dock.update(rect.adjusted(0,-2,0,3).toAlignedRect())

    def sync_clock(self):
        self.clock.stop()
        self.clock_sample.stop()
        if self.dock.cfg.get('dock_clock',True) and self.dock.isVisible():
            self.schedule_clock()
            if not self.dock.preview:
                self.clock_sample.start(80)
    def schedule_clock(self):
        now = datetime.datetime.now()
        self.clock_day = now.date()
        upper, _ = self.clock_content(now)
        step = 1 if self.dock.cfg['dock_clock_seconds'] else ROTATE_SECONDS if len(upper)>1 else 60
        self.clock.start(max(1,(step-now.second%step)*1000-now.microsecond//1000))

    def minute(self):
        rect=self.rects().get('clock')
        if rect and self.dock.isVisible():
            if datetime.datetime.now().date() != self.clock_day:
                self.dock.refresh_geometry()
                self.dock.update()
            else:
                self.dock.update(rect.toAlignedRect())
            self.schedule_clock()
    def close(self):
        self.clock.stop()
        self.clock_sample.stop()
        if self.popup:self.popup.close();self.popup.deleteLater();self.popup=None
