"""Precomposed icon reflections and lightweight, native Dock utility controls."""
import math,datetime
from PyQt5.QtCore import QObject,QTimer,Qt,QRectF,QPointF,QSize,QPoint,QMimeData,QEvent
from PyQt5.QtGui import QPixmap,QPainter,QColor,QLinearGradient,QFont,QPen,QDrag
from PyQt5.QtWidgets import QDialog,QPushButton,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QApplication,QStackedWidget,QWidget,QFrame

from quick_actions import ACTIONS,DEFAULT_ORDER,MIME,normalize_order

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
        from PyQt5.QtGui import QPainterPath
        path=QPainterPath(QPointF(13,2));path.lineTo(5,14);path.lineTo(11,14);path.lineTo(10,22);path.lineTo(19,9);path.lineTo(13,9);path.closeSubpath();p.drawPath(path)
    elif kind=='notes':
        p.drawRoundedRect(QRectF(4,3,16,18),2,2);p.drawLine(8,8,16,8);p.drawLine(8,12,16,12);p.drawLine(8,16,13,16)
    elif kind=='clock':p.drawEllipse(QRectF(3,3,18,18));p.drawLine(12,6,12,12);p.drawLine(12,12,17,14)
    elif kind=='calendar':
        p.drawRoundedRect(QRectF(3,5,18,16),2,2);p.drawLine(3,10,21,10);p.drawLine(8,3,8,7);p.drawLine(16,3,16,7)
        for x in (8,13,18):p.drawPoint(x,14);p.drawPoint(x,18)
    elif kind=='reflection':p.drawRoundedRect(QRectF(7,2,10,9),2,2);p.drawLine(3,14,21,14);p.drawLine(8,18,16,18);p.drawLine(10,21,14,21)
    elif kind=='blur':
        for x in (5,12,19):
            for y in (5,12,19):p.drawEllipse(QPointF(x,y),1.2 if x==5 else 1.8,1.2 if x==5 else 1.8)
    elif kind=='corner':p.drawArc(3,3,18,18,90*16,90*16);p.drawLine(3,12,3,21);p.drawLine(12,3,21,3)
    elif kind=='lite':
        p.drawRoundedRect(QRectF(2,6,19,12),3,3);p.drawLine(23,10,23,14);p.drawLine(8,10,8,14);p.drawLine(12,10,12,14)
    else:p.drawRoundedRect(QRectF(3,4,18,16),2,2);p.drawLine(6,9,18,9);p.drawLine(9,6,9,18)
    p.restore()


class QuickTile(QPushButton):
    def __init__(self,popup,key,title,kind):
        super().__init__(popup);self.popup=popup;self.key=key;self.title=title;self.kind=kind;self.value='';self.active=False
        self.setObjectName('QuickTile')
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
        if not self.popup.editing:return
        from ui_style import AlignedMenu
        menu=AlignedMenu(self);order=self.popup.order();page=order.index(self.key)//9
        previous=menu.addAction('移到上一页');previous.setEnabled(page>0);previous.triggered.connect(lambda:self.popup.move_to_page(self.key,page-1))
        following=menu.addAction('移到下一页');following.setEnabled(page<self.popup.pages.count()-1);following.triggered.connect(lambda:self.popup.move_to_page(self.key,page+1))
        first=order[page*9];menu.addAction('移到本页开头').triggered.connect(lambda:self.popup.move_action(self.key,first))
        menu.exec_(event.globalPos());menu.deleteLater()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);colors=self.popup.colors();accent=colors['accent']
        rect=QRectF(self.rect()).adjusted(1,1,-1,-1)
        background=QColor('#dceaf2' if colors['light'] else '#34434d') if self.active else QColor('#e9f0f5' if colors['light'] else '#28333b') if self.underMouse() else QColor('#f0f5f8' if colors['light'] else '#232b31')
        if self.isDown():background.setAlpha(65)
        p.setPen(Qt.NoPen);p.setBrush(background);p.drawRoundedRect(rect,8,8)
        ink=accent if self.active else colors['ink'];symbol(p,QRectF((self.width()-25)/2,11,25,25),self.kind,ink)
        font=QFont('Microsoft YaHei UI');font.setPixelSize(12);font.setWeight(QFont.DemiBold);p.setFont(font);p.setPen(colors['ink'])
        p.drawText(QRectF(3,42,self.width()-6,18),Qt.AlignCenter,self.title)
        font.setPixelSize(10);font.setWeight(QFont.Normal);p.setFont(font);p.setPen(colors['muted'])
        p.drawText(QRectF(3,62,self.width()-6,15),Qt.AlignCenter,self.value)
        if self.popup.editing:
            p.setPen(Qt.NoPen);p.setBrush(colors['muted'])
            for x in (self.width()-12,self.width()-8):
                for y in (8,12,16):p.drawEllipse(QPointF(x,y),.8,.8)


class PageTurnButton(QPushButton):
    def __init__(self,popup,direction,text):
        super().__init__(text,popup);self.popup=popup;self.direction=direction
        self.setStyleSheet('min-width:24px;max-width:24px;min-height:22px;max-height:22px;padding:0;font-size:18px;');self.setAcceptDrops(True)
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
        self.setAttribute(Qt.WA_TranslucentBackground);self.setAttribute(Qt.WA_NoMouseReplay);self.setFixedSize(320,402)
        self.editing=False;self._wheel_delta=0;self._bound_taskbar=None
        body=QVBoxLayout(self);body.setContentsMargins(16,12,16,12);body.setSpacing(9)
        header=QHBoxLayout();self.title=QLabel('快捷设置');self.title.setStyleSheet('font-size:15px;font-weight:600;background:transparent;');header.addWidget(self.title);header.addStretch()
        self.reset_button=QPushButton('重置');self.reset_button.setStyleSheet('min-width:30px;max-width:38px;padding:2px;min-height:22px;');self.reset_button.clicked.connect(self.reset_order);header.addWidget(self.reset_button);self.reset_button.hide()
        self.edit_button=QPushButton('排序');self.edit_button.setStyleSheet('min-width:30px;max-width:38px;padding:2px;min-height:22px;');self.edit_button.clicked.connect(self.toggle_edit);header.addWidget(self.edit_button)
        close=QPushButton('×');close.setFixedSize(25,25);close.setStyleSheet('border:0;background:transparent;padding:0;font-size:20px;');close.clicked.connect(self.close);header.addWidget(close);body.addLayout(header)
        self.pages=QStackedWidget();self.pages.setObjectName('QuickPages');self.pages.setFrameShape(QFrame.NoFrame);self.pages.setAutoFillBackground(False)
        self.pages.setStyleSheet('QStackedWidget#QuickPages,QWidget#QuickPage {background:transparent;border:0;}')
        self.page_grids=[]
        for _ in range(math.ceil(len(ACTIONS)/9)):
            page=QWidget();page.setObjectName('QuickPage');grid=QGridLayout(page);grid.setContentsMargins(0,0,0,0);grid.setSpacing(7)
            for row in range(3):grid.setRowStretch(row,1)
            for column in range(3):grid.setColumnStretch(column,1)
            self.pages.addWidget(page);self.page_grids.append(grid)
        self.tiles={key:QuickTile(self,key,title,kind) for key,title,kind in ACTIONS}
        body.addWidget(self.pages,1)
        footer=QHBoxLayout();hint=QLabel('滚轮翻页');hint.setStyleSheet('background:transparent;font-size:10px;');footer.addWidget(hint);footer.addStretch()
        self.prev_button=PageTurnButton(self,-1,'‹');self.next_button=PageTurnButton(self,1,'›');self.page_label=QLabel('1 / 2');self.page_label.setAlignment(Qt.AlignCenter);self.page_label.setStyleSheet('background:transparent;font-size:11px;')
        footer.addWidget(self.prev_button);footer.addWidget(self.page_label);footer.addWidget(self.next_button);body.addLayout(footer)
        self.status=QLabel('更改即保存 · 点击「排序」可调整按钮位置');self.status.setStyleSheet('background:transparent;font-size:10px;');body.addWidget(self.status)
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
        return super().eventFilter(watched,event)
    def order(self):return normalize_order(self.dock.cfg.get('dock_quick_order'))
    def rebuild_pages(self):
        current=self.pages.currentIndex()
        for grid in self.page_grids:
            while grid.count():grid.takeAt(0)
        for index,key in enumerate(self.order()):
            tile=self.tiles[key];tile.hide();self.page_grids[index//9].addWidget(tile,index%9//3,index%3);tile.show()
        self._shown_order=tuple(self.order())
        self.set_page(max(0,current))
    def set_page(self,page):
        page=max(0,min(page,self.pages.count()-1));self.pages.setCurrentIndex(page)
        self.prev_button.setEnabled(page>0);self.next_button.setEnabled(page<self.pages.count()-1)
        self.page_label.setText(str(page+1)+' / '+str(self.pages.count()))
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
        self.status.setText('拖动交换位置 · 拖到翻页按钮切页，或右键跨页移动' if self.editing else '更改即保存 · 点击「排序」可调整按钮位置')
        self.status.setWordWrap(self.editing)
        for tile in self.tiles.values():tile.setCursor(Qt.OpenHandCursor if self.editing else Qt.PointingHandCursor);tile.update()
    def valid_drag(self,event):
        source=event.source()
        return bool(self.editing and isinstance(source,QuickTile) and source.popup is self and event.mimeData().hasFormat(MIME) and bytes(event.mimeData().data(MIME))==source.key.encode('ascii'))
    def save_order(self,order):
        import sys
        from settings_effects import save_changes
        if not save_changes(self.dock.tray,sys.modules[self.dock.__class__.__module__],{'dock_quick_order':order}):self.status.setText('顺序保存失败，原顺序未改变。');return False
        self.rebuild_pages();return True
    def move_action(self,source,target):
        order=self.order()
        if source not in order or target not in order or source==target:return False
        left,right=order.index(source),order.index(target);order[left],order[right]=order[right],order[left]
        return self.save_order(order)
    def move_to_page(self,key,page):
        if key not in self.tiles or page<0 or page>=self.pages.count():return False
        order=self.order();order.remove(key);order.insert(min(page*9,len(order)),key)
        if not self.save_order(order):return False
        self.set_page(page);return True
    def reset_order(self):return self.save_order(list(DEFAULT_ORDER))
    def colors(self):
        light=self.dock.is_light();accent=QColor(self.dock.cfg.get('theme_color') or '#5f9fc8')
        if accent.lightness()>195:accent=accent.darker(145)
        return {'light':light,'accent':accent,'ink':QColor('#233c4c' if light else '#f1f6fa'),'muted':QColor('#526571' if light else '#b1c8d6')}
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);colors=self.colors();rect=QRectF(self.rect()).adjusted(1,1,-1,-1)
        p.setBrush(QColor('#ffffff' if colors['light'] else '#202124'))
        p.setPen(QPen(QColor('#dbe3e8' if colors['light'] else '#44474e'),1));p.drawRoundedRect(rect,16,16)
    def refresh(self):
        if tuple(self.order())!=getattr(self,'_shown_order',None):self.rebuild_pages()
        from appearance_profiles import MODES as PROFILE_MODES, selected_mode
        cfg=self.dock.cfg;runtime=getattr(self.dock.tray,'runtime',None)
        current=selected_mode(cfg)
        preset=next(name for name,mode in PROFILE_MODES if mode==current)
        values={'settings':'完整选项','add':'应用 / 快捷方式','manage':'批量添加 / 移除','appearance':preset,
                'size':str(cfg['icon_size'])+' 像素','position':{'bottom':'底部','top':'顶部','custom':'自定义'}.get(cfg['position'],'底部'),
                'panels':'已开启' if cfg['panel_enabled'] else '已关闭','magnify':'已开启' if cfg['magnify'] else '已关闭',
                'lite':'已开启' if runtime and runtime.lite else '已关闭',
                'notes':'已开启' if cfg['notes_enabled'] and cfg['notes_visible'] else '已关闭',
                'clock':'已开启' if cfg['clock_enabled'] else '已关闭','calendar':'已开启' if cfg['calendar_enabled'] else '已关闭',
                'reflections':'已开启' if cfg['dock_reflections'] else '已关闭','dock_time':'已开启' if cfg['dock_clock'] else '已关闭',
                'color_mode':{'auto':'跟随系统','light':'浅色','dark':'深色'}.get(cfg['theme'],'跟随系统'),
                'blur':'已开启' if cfg['glass'] else '已关闭','panel_auto_hide':'已开启' if cfg['panel_auto_hide'] else '已关闭',
                'corners':'已开启' if cfg['screen_corners'] else '已关闭',
                'search':'应用 / 文件 / 便签','undo':'暂无可撤销',
                'layouts':'保存 / 切换布局','references':'检查 / 重新定位'}
        values['taskbar_monitor']='已开启' if cfg['resource_taskbar'] else '已关闭'
        values['resources']='查看系统读数' if cfg['resource_enabled'] else '打开资源监控'
        self.tiles['resources'].setToolTip('打开资源详情，右键可以切换层级、收起形态和采样项目。')
        values['flash']='记一条闪念' if not cfg['flash_enabled'] else '%d 条未完成'%sum(not r['done'] and not r['deleted'] for r in cfg['flash_entries'])
        self.tiles['flash'].setToolTip('打开闪念胶囊并输入。可在桌面收纳设置中调整配色或关闭。')
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
        self.tiles['taskbar_text'].setToolTip('点击循环切换：跟随系统 → 白字 → 黑字。\n联动 Windows 明暗模式及开始菜单，普通应用配色保留。')
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
        for key,tile in self.tiles.items():tile.value=values[key];tile.active=values[key]=='已开启';tile.update()
        colors=self.colors();self.title.setStyleSheet('background:transparent;font-size:15px;font-weight:600;color:'+colors['ink'].name())
        self.status.setStyleSheet('background:transparent;font-size:10px;color:'+colors['muted'].name());self.update()
    def showEvent(self, event):
        super().showEvent(event)
        taskbar = self._bound_taskbar
        if hasattr(taskbar, 'reconcile_status'):
            taskbar.reconcile_status()

    def taskbar_status_changed(self,message):
        self.refresh()
        error=getattr(self._bound_taskbar,'error','')
        self.status.setText('任务栏效果应用失败，请查看提示。' if error else str(message))
        self.status.setToolTip(str(error) if error else '')

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
        self.status.setToolTip('')
        if key=='taskbar_monitor':
            if runtime:runtime.resources.set_options(resource_taskbar=not runtime.dock.cfg['resource_taskbar'])
            self.refresh();return
        if key=='resources':
            self.close()
            if runtime:runtime.resources.open()
            return
        if key=='flash':
            self.close()
            if runtime:runtime.flash.open(compose=True)
            return
        if key in ('search','undo','layouts','references'):
            service=getattr(runtime,'productivity',None)
            if service is None or getattr(service,'closed',False):
                self.status.setText('整理工具暂不可用，请重新打开设置。');return
            if key=='undo':
                service.undo();self.refresh();self.reanchor()
                self.status.setText(service.message);self.status.setToolTip(service.message);return
            method={'search':'open_search','layouts':'open_layouts','references':'open_references'}[key]
            self.close();getattr(service,method)();return
        if key in ('settings','add','manage'):
            self.close()
            if key=='settings':(runtime.show_settings if runtime else tray.show_settings)()
            elif key=='add':tray.add_icons()
            elif hasattr(tray,'importer'):tray.importer.show()
            return
        if key=='lite' and runtime:runtime.set_lite(not runtime.lite);self.refresh();return
        cfg=self.dock.cfg;changes={}
        if key in ('appearance','size','position'):
            notes = getattr(runtime, 'notes', None)
            if key == 'appearance' and notes and not notes.flush():
                self.status.setText('便签保存失败，外观切换已取消。');return
            from quick_cycles import next_cycle
            changes=next_cycle(cfg,key)
        elif key=='panels':changes={'panel_enabled':not cfg['panel_enabled'],'panels_visible':True}
        elif key=='magnify':changes={'magnify':not cfg['magnify']}
        elif key=='notes':changes={'notes_enabled':not (cfg['notes_enabled'] and cfg['notes_visible']),'notes_visible':True}
        elif key=='clock':changes={'clock_enabled':not cfg['clock_enabled']}
        elif key=='calendar':changes={'calendar_enabled':not cfg['calendar_enabled']}
        elif key=='reflections':changes={'dock_reflections':not cfg['dock_reflections']}
        elif key=='dock_time':changes={'dock_clock':not cfg['dock_clock']}
        elif key=='color_mode':
            modes=('auto','light','dark');changes={'theme':modes[(modes.index(cfg['theme'])+1)%3]}
        elif key=='blur':changes={'glass':not cfg['glass']}
        elif key=='panel_auto_hide':changes={'panel_auto_hide':not cfg['panel_auto_hide']}
        elif key=='taskbar_text':
            from taskbar_text import MODES
            modes = [value for title, value in MODES]
            current = cfg.get('taskbar_text_mode', 'system')
            index = modes.index(current) if current in modes else 0
            changes = {'taskbar_text_mode': modes[(index+1) % len(modes)]}
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
            if not save_changes(tray,sys.modules[self.dock.__class__.__module__],changes):self.status.setText('保存失败，未应用更改。');return
        if key=='notes' and changes.get('notes_enabled') and runtime:
            notes=getattr(runtime,'notes',None)
            if notes and not notes.rows() and notes.new() is None:self.status.setText('便签已启用，但新建失败，请在便签管理中重试。')
        self.refresh();self.reanchor()
        if key=='taskbar':
            taskbar=getattr(runtime,'taskbar',None)
            self.taskbar_status_changed(getattr(taskbar,'status','任务栏效果配置已保存。'))
        if key=='taskbar_text':
            error = getattr(getattr(getattr(runtime,'taskbar',None),'text',None),'error','')
            self.status.setText('任务栏文字应用失败，请查看提示。' if error else '文字颜色已保存 · 联动 Windows 明暗模式')
            self.status.setToolTip(str(error) if error else '')


    def enable_taskbar_component(self, tray, taskbar):
        if not getattr(taskbar, 'payload', None):
            self.status.setText(getattr(taskbar, 'status', '任务栏组件未就绪。'))
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
                self.status.setText(message)

        if taskbar.install_offline(installed):
            self.refresh()
            self.status.setText('正在离线安装任务栏组件…')


class DockExtras(QObject):
    def __init__(self,dock):
        super().__init__(dock);self.dock=dock;self.popup=None;self.pressed=None;self.hover=None
        self.clock=QTimer(self);self.clock.setSingleShot(True);self.clock.timeout.connect(self.minute)
    def reflection_room(self):return max(2,round(self.dock.icon_size*.32)) if self.dock.cfg.get('dock_reflections',True) and self.dock.items else 0
    def bottom_space(self):
        return max(1,round((self.dock.pad_y+self.reflection_room())/2)) if self.reflection_room() else self.dock.pad_y
    def prepare(self,items):
        icons=[it for it in items if not it.get('sep') and it.get('pixmap') is not None]
        limit=min(128,max(24,int(math.sqrt(REFLECTION_BUDGET/max(1,len(icons))/5.6))))
        for item in icons:
            source=item['pixmap'];key=(source.cacheKey(),limit)
            if not self.dock.cfg.get('dock_reflections',True):item.pop('_reflected',None);item.pop('_reflection_key',None);continue
            if source.isNull():continue
            if item.get('_reflection_key')!=key:
                item['_reflected'],item['_reflection_ratio']=compose_reflection(source,limit);item['_reflection_key']=key
    def width(self):
        d=self.dock;gap=max(7,round(d.icon_size*.22));side=max(27,min(48,round(d.icon_size*.88)))
        widths=([max(70,min(128,round(d.icon_size*1.85)))] if d.cfg.get('dock_clock',True) else [])
        widths+=([side] if d.cfg.get('dock_quick_settings',True) else [])+([side] if d.cfg.get('dock_add_button',True) else [])
        return sum(widths)+gap*len(widths) if widths else 0
    def rects(self):
        d=self.dock;bar=d.bar_rect_f();x=bar.right()-d.pad_x-self.width();gap=max(7,round(d.icon_size*.22));side=max(27,min(48,round(d.icon_size*.88)))
        cy=bar.top()+d.pad_y+d.icon_size/2;out={}
        for key,on,width in [('clock',d.cfg.get('dock_clock',True),max(70,min(128,round(d.icon_size*1.85)))),('quick',d.cfg.get('dock_quick_settings',True),side),('add',d.cfg.get('dock_add_button',True),side)]:
            if on:x+=gap;out[key]=QRectF(x,cy-side/2,width,side);x+=width
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
                font=QFont('Segoe UI');font.setPixelSize(max(12,min(21,round(d.icon_size*.39))));font.setWeight(QFont.DemiBold);p.setFont(font);p.setPen(ink)
                p.drawText(rect.adjusted(0,-2,0,-rect.height()*.38),Qt.AlignCenter,now.strftime('%H:%M'))
                font.setPixelSize(max(9,min(12,round(d.icon_size*.23))));font.setWeight(QFont.Normal);p.setFont(font)
                label=now.strftime('%m月%d日')+' '+('周'+'一二三四五六日'[now.weekday()]);p.drawText(rect.adjusted(0,rect.height()*.51,0,3),Qt.AlignCenter,label)
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
    def sync_clock(self):
        self.clock.stop()
        if self.dock.cfg.get('dock_clock',True) and self.dock.isVisible():
            now=datetime.datetime.now();self.clock.start(max(100,60000-now.second*1000-now.microsecond//1000))
    def minute(self):
        rect=self.rects().get('clock')
        if rect:self.dock.update(rect.toAlignedRect())
        self.sync_clock()
    def close(self):
        self.clock.stop()
        if self.popup:self.popup.close();self.popup.deleteLater();self.popup=None
