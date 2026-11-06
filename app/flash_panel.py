"""Interactive edge handle, flash inbox and non-activating reminder on Windows."""
import datetime as dt
from PyQt5.QtCore import Qt, QTimer, QSize, QPoint, QRect, QRectF, QDateTime,QVariantAnimation,QEasingCurve
from PyQt5.QtGui import QColor, QPainter, QPen, QCursor, QKeySequence, QFont, QRegion, QPainterPath, QPalette
from PyQt5.QtWidgets import (QWidget,QFrame,QDialog,QLabel,QLineEdit,QPushButton,QVBoxLayout,QHBoxLayout,
    QListWidgetItem,QPlainTextEdit,QShortcut,QMessageBox,QApplication,QToolButton,QDateTimeEdit,QSizePolicy)
from flash_data import COLORS, filtered, MAX_TEXT
from flash_view import (palette_for, text_ink, icon, tool, Swatch, IdeaEditor, CapsuleDelegate,
                        CapsuleList, plain_drop, copy_drop, color_icon, ToolGlass)
from screen_layout import screen_records, choose_screen, capture, project
from ui_style import ModernComboBox, AlignedMenu


TOOL_FLAGS=Qt.Tool|Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint|Qt.NoDropShadowWindowHint


def rounded_window(widget):
    widget.setAttribute(Qt.WA_TranslucentBackground)
    widget.setAttribute(Qt.WA_ShowWithoutActivating)


def moment(stamp):
    return QDateTime.fromSecsSinceEpoch(stamp).toLocalTime().toString('MM月dd日 HH:mm')


def ask_time(parent):
    box=QDialog(parent);box.setWindowTitle('闪念提醒 · 大肥鱼Dock')
    layout=QVBoxLayout(box);layout.addWidget(QLabel('提醒时间',box))
    field=QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600),box)
    field.setDisplayFormat('yyyy-MM-dd HH:mm');field.setCalendarPopup(True)
    field.setMinimumDateTime(QDateTime.currentDateTime().addSecs(1))
    layout.addWidget(field)
    row=QHBoxLayout();row.addStretch()
    cancel=QPushButton('取消');save=QPushButton('保存提醒')
    cancel.clicked.connect(box.reject);save.clicked.connect(box.accept)
    row.addWidget(cancel);row.addWidget(save);layout.addLayout(row)
    try:return field.dateTime().toSecsSinceEpoch() if box.exec_()==QDialog.Accepted else None
    finally:box.deleteLater()


class EdgeHandle(QWidget):
    def __init__(self,service):
        super().__init__(None,TOOL_FLAGS|Qt.WindowDoesNotAcceptFocus)
        self.service=service;self.press=None;self.moving=False;self.dragging_text=False;self.notice=''
        self.setObjectName('FlashEdge');self.setWindowTitle('闪念胶囊');self.setAccessibleName('闪念胶囊贴边入口')
        rounded_window(self);self.setFixedSize(29,68);self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self.hover=QTimer(self);self.hover.setSingleShot(True);self.hover.setInterval(200)
        self.hover.timeout.connect(self.open_on_hover)
        self.notice_timer=QTimer(self);self.notice_timer.setSingleShot(True)
        self.notice_timer.timeout.connect(self.clear_notice)

    def update_count(self):
        self.count=sum(not r['done'] and not r['deleted'] for r in self.service.cfg['flash_entries'])
        self.setToolTip('闪念胶囊 · %d 条未完成\n点击速记，沿边缘拖动可调整位置。'%self.count)
        self.update()

    def feedback(self,text):
        self.notice=text;self.setToolTip(text);self.update();self.notice_timer.start(1400)

    def clear_notice(self):
        self.notice='';self.update_count()

    def place(self,point=None):
        screens=screen_records()
        if not screens:return
        record=self.service.cfg.get('flash_layout',{})
        if point is None:
            target=choose_screen(record,screens)
        else:
            reference=capture([point.x(),point.y(),1,1],screens)
            target=choose_screen(reference,screens)
        x,y,w,h=target['area']
        projected=project(record,screens,minimum=(1,1)) if record and point is None else None
        top=point.y()-self.press.y() if point is not None and self.press is not None else (
            projected[1]+projected[3]//2-self.height()//2 if projected else y+(h-self.height())//2)
        left=x+2 if self.service.cfg['flash_side']=='left' else x+w-self.width()-2
        self.move(left,max(y,min(top,y+h-self.height())))
        self.work_area=QRect(x,y,w,h)

    def paintEvent(self,event):
        colors=palette_for(self.service)
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);p.setRenderHint(QPainter.TextAntialiasing)
        rect=QRectF(self.rect()).adjusted(1.5,1.5,-1.5,-1.5)
        p.setBrush(QColor(colors['surface']));p.setPen(QPen(QColor(colors['line']),1))
        p.drawRoundedRect(rect,rect.width()/2,rect.width()/2)
        fg=QColor(colors['ink']);p.setPen(fg)
        font=QFont(self.font());font.setPixelSize(12);font.setWeight(QFont.DemiBold);p.setFont(font)
        x=round(rect.center().x());y=round(rect.top()+13);sign=1 if self.service.cfg['flash_side']=='left' else -1
        p.setPen(QPen(fg,1.5));p.drawLine(x-sign*2,y-4,x+sign*2,y);p.drawLine(x+sign*2,y,x-sign*2,y+4)
        if self.dragging_text or self.notice=='已记下闪念':
            p.drawText(rect.adjusted(0,18,0,-4),Qt.AlignCenter,'＋' if self.dragging_text else '✓')
        else:
            p.drawText(rect.adjusted(0,18,0,-22),Qt.AlignCenter,'闪')
            p.drawText(rect.adjusted(0,36,0,-4),Qt.AlignCenter,'念')

    def open_on_hover(self):
        if self.press is None and not self.dragging_text and self.rect().contains(self.mapFromGlobal(QCursor.pos())):
            self.service.open(activate=False)

    def enterEvent(self,event):
        self.hover.start()
        if self.service.panel:self.service.panel.fold.stop()
        super().enterEvent(event)

    def leaveEvent(self,event):
        self.hover.stop()
        if self.service.panel:self.service.panel.arm_fold()
        super().leaveEvent(event)

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:
            self.hover.stop();self.press=event.pos();self.moving=False;event.accept()
        else:super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self.press is None or not event.buttons()&Qt.LeftButton:return
        if (event.globalPos()-self.mapToGlobal(self.press)).manhattanLength()>=QApplication.startDragDistance():
            self.moving=True
        if self.moving:
            self.place(event.globalPos())
            if self.service.panel:self.service.panel.place(self)

    def mouseReleaseEvent(self,event):
        if event.button()!=Qt.LeftButton or self.press is None:return
        self.press=None
        if self.moving:
            self.moving=False
            if not self.service.persist(flash_layout=capture(list(self.geometry().getRect()),screen_records())):
                self.service.reposition()
        else:self.service.open(compose=True)

    def dragEnterEvent(self,event):
        if self.service.cfg['flash_drop'] and plain_drop(event.mimeData()) and event.possibleActions()&Qt.CopyAction:
            self.hover.stop();self.dragging_text=True;self.update();copy_drop(event)
        else:event.ignore()
    def dragLeaveEvent(self,event):
        self.dragging_text=False;self.update();super().dragLeaveEvent(event)
    def dropEvent(self,event):
        self.dragging_text=False;self.update()
        if self.service.cfg['flash_drop'] and event.possibleActions()&Qt.CopyAction and self.service.add(plain_drop(event.mimeData())):
            copy_drop(event)
        else:event.ignore()
    def contextMenuEvent(self,event):
        menu=AlignedMenu(self)
        menu.addAction('记一条闪念',lambda:self.service.open(compose=True))
        menu.addAction('查看闪念',lambda:self.service.open())
        menu.addSeparator();menu.addAction('隐藏贴边胶囊',lambda:self.service.set_enabled(False))
        try:menu.exec_(event.globalPos())
        finally:menu.deleteLater()
    def dismiss(self):
        self.hover.stop();self.notice_timer.stop();self.hide();self.deleteLater()


class FlashPanel(QWidget):
    def __init__(self,service):
        super().__init__(None,TOOL_FLAGS)
        self.service=service;self.expanded='';self.color_filter='';self.editing=False;self.edit_id=''
        self.edit_color=service.cfg['flash_color'];self.rows={};self.icons={};self.hold=False
        rounded_window(self);self.setAcceptDrops(True);self.setWindowTitle('闪念胶囊 · 大肥鱼Dock')
        outer=QVBoxLayout(self);outer.setContentsMargins(1,1,1,1)
        self.surface=QFrame();self.surface.setObjectName('FlashSurface');outer.addWidget(self.surface)
        content=QVBoxLayout(self.surface);content.setContentsMargins(3,2,3,2);content.setSpacing(4)
        self.browse=QWidget();content.addWidget(self.browse,1)
        body=QVBoxLayout(self.browse);body.setContentsMargins(0,0,0,0);body.setSpacing(4)
        self.list_extent=0
        self.tools_slot=QWidget();self.tools_slot.setFixedHeight(26);body.addWidget(self.tools_slot)
        tools_row=QHBoxLayout(self.tools_slot);tools_row.setContentsMargins(0,0,0,0);tools_row.setSpacing(0);tools_row.addStretch()
        self.launch_shell=ToolGlass(self);launch=QHBoxLayout(self.launch_shell);launch.setContentsMargins(2,0,2,0)
        self.launcher=tool('more','闪念操作',self.toggle_tools,'#293740');self.launcher.setFixedSize(22,24);launch.addWidget(self.launcher)
        self.toolbar=ToolGlass(self);header=QHBoxLayout(self.toolbar);header.setContentsMargins(4,0,4,0);header.setSpacing(1)
        self.tools={}
        for symbol,title,callback in [('plus','记一条（Ctrl+N）',self.begin_edit),('filter','按颜色或状态筛选',self.toggle_filters),
                                      ('search','搜索闪念（Ctrl+F）',self.focus_search),('more','更多闪念操作',self.more_menu),('fold','收起到屏幕边缘',self.service.collapse)]:
            item=tool(symbol,title,callback,'#293740');item.setFixedSize(23,24);header.addWidget(item);self.tools[symbol]=item
        self.add=self.tools['plus'];self.fold_button=self.tools['fold']
        tools_row.addWidget(self.launch_shell);tools_row.addWidget(self.toolbar)
        self.launch_shell.hide();self.toolbar.hide()
        self.tools_timer=QTimer(self);self.tools_timer.setSingleShot(True);self.tools_timer.setInterval(1100)
        self.tools_timer.timeout.connect(self.hide_tools)
        self.search=QLineEdit();self.search.setObjectName('FlashSearch');self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName('搜索闪念');self.search.setPlaceholderText('搜索闪念');self.search.textChanged.connect(self.render)
        body.addWidget(self.search);self.search.hide()
        self.filters_bar=ToolGlass(self);filters=QHBoxLayout(self.filters_bar);filters.setContentsMargins(5,1,5,1);filters.setSpacing(2)
        self.view=ModernComboBox();self.view.setAccessibleName('闪念状态')
        for title,key in [('未完成','open'),('已完成','done'),('回收站','trash')]:self.view.addItem(title,key)
        self.view.setFixedWidth(96);self.view.currentIndexChanged.connect(self.render);filters.addWidget(self.view)
        self.all_colors=QPushButton('全部');self.all_colors.setObjectName('FlashAll');self.all_colors.setCheckable(True)
        self.all_colors.setAccessibleName('全部颜色');self.all_colors.clicked.connect(lambda:self.select_color(''));filters.addWidget(self.all_colors)
        self.swatches={}
        for key in COLORS:
            self.swatches[key]=Swatch(key,self.select_color);filters.addWidget(self.swatches[key])
        body.addWidget(self.filters_bar,0,Qt.AlignRight);self.filters_bar.hide()

        self.composer=ToolGlass(self,corner=13);self.composer.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        stack=QVBoxLayout(self.composer);stack.setContentsMargins(10,7,10,7);stack.setSpacing(3)
        self.editor=IdeaEditor();self.editor.submit.connect(self.submit);self.editor.textChanged.connect(self.draft_changed)
        self.editor.height_changed.connect(self.reflow);self.editor.setToolTip('Enter 保存，Shift+Enter 换行')
        self.editor.too_long.connect(lambda:self.message(f'每条闪念最多 {MAX_TEXT} 个字，请分条保存。'))
        stack.addWidget(self.editor)
        command=QHBoxLayout();self.color_button=QToolButton();self.color_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.color_button.setAccessibleName('本条闪念颜色');self.color_button.clicked.connect(self.choose_draft_color);command.addWidget(self.color_button)
        command.addStretch();forget=QPushButton('放弃');forget.clicked.connect(self.discard);command.addWidget(forget)
        save=QPushButton('保存');save.setObjectName('FlashSave');save.setToolTip('Enter 保存，Shift+Enter 换行');save.clicked.connect(self.submit);command.addWidget(save)
        stack.addLayout(command);content.addWidget(self.composer);self.composer.hide()
        self.list=CapsuleList(self);self.list.setItemDelegate(CapsuleDelegate(self))
        self.list.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Ignored);self.list.setMinimumHeight(0);body.addWidget(self.list,1)
        self.empty=QLabel();self.empty.setObjectName('FlashEmpty');self.empty.setAlignment(Qt.AlignCenter);self.empty.setWordWrap(True);body.addWidget(self.empty,0,Qt.AlignRight|Qt.AlignTop)
        self.clear_trash=QPushButton('清空回收站');self.clear_trash.clicked.connect(self.confirm_empty)
        body.addWidget(self.clear_trash,0,Qt.AlignRight)
        self.status=QLabel();self.status.setObjectName('FlashStatus');self.status.setWordWrap(True)
        self.status.setAlignment(Qt.AlignCenter);content.addWidget(self.status,0,Qt.AlignRight);self.status.hide()
        self.notice_timer=QTimer(self);self.notice_timer.setSingleShot(True);self.notice_timer.timeout.connect(self.hide_notice)
        self.mask_timer=QTimer(self);self.mask_timer.setSingleShot(True);self.mask_timer.timeout.connect(self.input_region)
        self.list.verticalScrollBar().valueChanged.connect(lambda *_:self.mask_timer.start(0))
        self.list.verticalScrollBar().rangeChanged.connect(lambda *_:self.mask_timer.start(0))
        self.fold=QTimer(self);self.fold.setSingleShot(True);self.fold.timeout.connect(self.fold_if_idle)
        self.draft_timer=QTimer(self);self.draft_timer.setSingleShot(True);self.draft_timer.setInterval(700)
        self.draft_timer.timeout.connect(service.save_draft)
        self.shortcuts=[]
        for keys,fn in [('Ctrl+N',self.begin_edit),('Ctrl+F',self.focus_search)]:
            key=QShortcut(QKeySequence(keys),self);key.setContext(Qt.WidgetWithChildrenShortcut);key.activated.connect(fn);self.shortcuts.append(key)
        self.recent='';self.pulse_level=0.
        self.pulse=QVariantAnimation(self);self.pulse.setDuration(350)
        self.pulse.setStartValue(1.);self.pulse.setEndValue(0.);self.pulse.setEasingCurve(QEasingCurve.OutCubic)
        self.pulse.valueChanged.connect(self.update_pulse)
        self.apply_style();self.render()

    def update_pulse(self,value):
        self.pulse_level=float(value)
        self.list.viewport().update()

    def apply_style(self):
        self.colors=palette_for(self.service);c=self.colors;self.icons.clear()
        self.launcher.setIcon(icon('more',c['ink']))
        for symbol,item in self.tools.items():item.setIcon(icon(symbol,c['ink']))
        for bar in (self.toolbar,self.launch_shell,self.filters_bar,self.composer):bar.update()
        self.editor.setProperty('allowTextDrop',self.service.cfg['flash_drop'])
        self.setStyleSheet("""
          QFrame#FlashSurface {background:transparent; border:0;} QWidget#qt_scrollarea_viewport {background:transparent;}
          QLabel {background:transparent; color:%(ink)s;}
          QLabel#FlashTitle {font-size:17px; font-weight:600;}
          QLabel#FlashStatus,QLabel#FlashEmpty {background:%(surface)s;color:%(muted)s;padding:4px 9px;border-radius:8px;font-size:12px;}
          QListWidget#FlashList {background:transparent; border:none; outline:0; padding:0;}
          QPlainTextEdit {background:transparent; color:%(ink)s; border:0; padding:2px; font-size:14px;}
          QLineEdit#FlashSearch {background:%(field)s; color:%(ink)s; border:1px solid %(line)s; border-radius:8px; padding:4px 8px; min-height:21px;}
          QComboBox {background:%(field)s; color:%(ink)s; border:1px solid %(line)s; border-radius:7px; padding:2px 19px 2px 7px; min-height:21px; font-size:12px;}
          QComboBox::drop-down {width:19px; border:0;}
          QPushButton,QToolButton {color:%(ink)s; background:transparent; border:0; border-radius:5px; padding:3px 6px; min-height:20px;}
          QPushButton:hover,QToolButton:hover,QPushButton#FlashAll:checked {background:%(hover)s;}
          QPushButton#FlashSave {background:%(ink)s; color:%(surface)s; font-weight:600; padding:3px 10px;}
        """%c)
        vp=self.list.viewport();vp.setAutoFillBackground(False);vp.setAttribute(Qt.WA_TranslucentBackground)
        pal=self.list.palette();pal.setColor(QPalette.Base,Qt.transparent);self.list.setPalette(pal)
        vp.setPalette(pal);self.surface.setAutoFillBackground(False)
        self.editor.fit_text();self.reflow()

    def input_region_later(self):
        if hasattr(self,'mask_timer'):self.mask_timer.start(0)

    def input_region(self):
        if not self.isVisible():return
        # A real native shape lets clicks through to Explorer between individual notes.
        region=QRegion()
        def box(widget,radius=7,local=None):
            nonlocal region
            if not widget.isVisible():return
            area=QRect(widget.mapTo(self,QPoint()),widget.size()) if local is None else local
            if area.isEmpty():return
            path=QPainterPath();path.addRoundedRect(QRectF(area.adjusted(-1,-1,1,1)),radius,radius)
            region|=QRegion(path.toFillPolygon().toPolygon())
        for widget in (self.toolbar,self.launch_shell,self.filters_bar,self.search,self.composer,self.empty,self.status,self.clear_trash):
            box(widget)
        vp=self.list.viewport();clip=vp.rect()
        if self.list.isVisible():
            top=self.list.indexAt(QPoint(2,1)).row()
            for i in range(max(0,top),self.list.count()):
                item=self.list.item(i);rect=self.list.visualItemRect(item)
                if rect.top()>clip.bottom():break
                row=self.rows[item.data(Qt.UserRole)]
                if row['id']==self.expanded:
                    detail=self.list.itemWidget(item)
                    if detail:rect=detail.geometry()
                else:
                    rect=self.list.itemDelegate().bubble(rect,self.list.fontMetrics(),item.text(),18 if row['pinned'] or row['due'] else 0).toAlignedRect()
                rect=rect.intersected(clip).translated(vp.mapTo(self,QPoint()))
                box(vp,12,rect)
        box(self.list.verticalScrollBar(),3)
        if region.isEmpty():region=QRegion(0,0,1,1)
        self.setMask(region)

    def showEvent(self,event):
        super().showEvent(event);self.input_region_later()
    def resizeEvent(self,event):
        super().resizeEvent(event);self.input_region_later()
    def toggle_tools(self):
        self.launch_shell.hide();self.toolbar.show();self.tools_timer.start();self.input_region_later()
    def hide_tools(self):
        if self.toolbar.isVisible() and self.toolbar.underMouse():
            self.tools_timer.start();return
        self.toolbar.hide();self.launch_shell.setVisible(not self.editing and self.underMouse());self.input_region_later()
    def toggle_filters(self):
        self.filters_bar.setVisible(not self.filters_bar.isVisible());self.reflow()
    def more_menu(self):
        target=self.menu_choice(self.tools['more'],[('open','未完成',None),('done','已完成',None),
            ('trash','回收站',None),('settings','闪念设置…',None),('off','关闭贴边胶囊',None)])
        if target in ('open','done','trash'):self.view.setCurrentIndex(self.view.findData(target))
        elif target=='settings':
            self.service.runtime.show_settings()
            self.service.runtime.tray.settings_dialog.focus_setting('flash_palette')
        elif target=='off':self.service.set_enabled(False)
    def hide_notice(self):
        self.status.hide();self.reflow()

    def row_icon(self,name,ink):
        key=(name,ink)
        if key not in self.icons:self.icons[key]=icon(name,ink)
        return self.icons[key]

    def reflow(self):
        if not hasattr(self,'mask_timer'):return
        if self.service.edge:self.place(self.service.edge)
        self.input_region_later()

    def place(self,edge):
        if not hasattr(edge,'work_area'):return
        area=edge.work_area
        width=max(1,min(368,area.width()-edge.width()-6))
        available=max(1,width-8)
        for label in (self.status,self.empty):
            if label.isHidden() or not label.text():continue
            metrics=label.fontMetrics()
            wanted=min(available,metrics.horizontalAdvance(label.text())+22)
            label.setFixedWidth(wanted)
            label.setFixedHeight(max(metrics.height()+10,label.heightForWidth(wanted)))
        for part in (self.composer,self.browse,self.surface,self):
            part.layout().invalidate();part.layout().activate()
        height=self.layout().sizeHint().height()
        if not self.editing:height+=self.list_extent
        height=max(1,min(height,452,area.height()-6))
        x=edge.geometry().left()-width if self.service.cfg['flash_side']=='right' else edge.geometry().right()+1
        y=max(area.top()+3,min(edge.geometry().center().y()-height//2,area.bottom()-height-2))
        rect=QRect(x,y,width,height)
        if rect!=self.geometry():self.setGeometry(rect)

    def focus_search(self):
        if self.editing:return
        self.search.show();self.search.setFocus();self.search.selectAll();self.reflow()
    def select_color(self,key):
        self.color_filter=key;self.filters_bar.hide();self.render()
    def message(self,text):
        self.status.setText(text);self.status.setToolTip(text);self.status.show();self.notice_timer.start(1900);self.reflow()

    def render(self,*args):
        pos=self.list.verticalScrollBar().value()
        rows=filtered(self.service.cfg['flash_entries'],self.view.currentData(),self.color_filter,self.search.text())
        self.rows={row['id']:row for row in rows}
        if self.expanded not in self.rows:self.expanded=''
        self.all_colors.setChecked(not self.color_filter)
        for key,swatch in self.swatches.items():swatch.setChecked(key==self.color_filter)
        self.list_extent=0
        self.list.setUpdatesEnabled(False)
        try:
            self.list.clear()
            for row in rows:
                text=' '.join(row['text'].split())[:220]
                item=QListWidgetItem(text);item.setData(Qt.UserRole,row['id'])
                item.setSizeHint(QSize(1,35));self.list.addItem(item)
                if self.expanded==row['id']:
                    detail=self.detail(row)
                    item.setSizeHint(QSize(1,detail.sizeHint().height()+3));self.list.setItemWidget(item,detail)
                self.list_extent+=item.sizeHint().height()
            self.list.verticalScrollBar().setValue(pos)
        finally:self.list.setUpdatesEnabled(True)
        self.list.setVisible(bool(rows));self.empty.setVisible(not rows)
        view=self.view.currentData()
        self.empty.setText('没有符合条件的闪念' if self.search.text() or self.color_filter else
                           {'open':'写下第一条闪念，或拖一段文字到这里。','done':'完成的闪念会出现在这里。','trash':'回收站是空的。'}.get(view,''))
        self.clear_trash.setVisible(view=='trash' and bool(rows))
        self.hide_notice();self.input_region_later()

    def expand(self,identity):
        self.expanded='' if self.expanded==identity else identity
        self.render()
        if self.expanded:
            for i in range(self.list.count()):
                item=self.list.item(i)
                if item.data(Qt.UserRole)==identity:self.list.scrollToItem(item);break

    def reveal_item(self,identity,expanded=True):
        row=self.service.item(identity)
        if not row:return
        self.color_filter='';self.search.clear();self.view.setCurrentIndex(2 if row['deleted'] else 1 if row['done'] else 0)
        self.expanded=identity if expanded else ''
        self.render()
        for i in range(self.list.count()):
            item=self.list.item(i)
            if item.data(Qt.UserRole)==identity:
                self.list.scrollToItem(item);break
        if not expanded and self.service.cfg['motion_enabled']:
            self.recent=identity;self.pulse.stop();self.pulse.start()

    def menu_choice(self,anchor,options):
        self.fold.stop();self.hold=True;menu=AlignedMenu(self);values={}
        for key,title,colour in options:
            action=menu.addAction(title)
            if colour:action.setIcon(color_icon(key))
            values[action]=key
        try:return values.get(menu.exec_(anchor.mapToGlobal(QPoint(0,anchor.height()))))
        finally:
            menu.deleteLater();self.hold=False;self.arm_fold()

    def color_choice(self,anchor):
        return self.menu_choice(anchor,[(key,name,rgb) for key,(name,rgb) in COLORS.items()])

    def detail(self,row):
        identity=row['id'];fill=self.colors['fills'][row['color']];ink=text_ink(fill)
        frame=QFrame();frame.setObjectName('FlashDetail')
        frame.setStyleSheet('QFrame#FlashDetail{background:%s;border:0;border-radius:13px;} QLabel,QToolButton,QPlainTextEdit{color:%s;background:transparent;border:0;} QToolButton{padding:2px 4px;min-height:21px;} QToolButton:hover{background:rgba(127,127,127,38);}'%(fill,ink))
        box=QVBoxLayout(frame);box.setContentsMargins(11,7,10,6);box.setSpacing(3)
        meta=QHBoxLayout();meta.setSpacing(4)
        stamp=QLabel(moment(row['created']));stamp.setStyleSheet('font-size:11px;');meta.addWidget(stamp);meta.addStretch()
        if row['due'] and not row['deleted']:
            badge=QLabel('提醒 '+moment(row['due']));badge.setStyleSheet('font-size:11px;');meta.addWidget(badge)
        collapse=tool('less','收起本条',lambda:self.expand(identity),ink);meta.addWidget(collapse);box.addLayout(meta)
        from PyQt5.QtGui import QTextDocument
        from PyQt5.QtWidgets import QSizePolicy
        doc=QTextDocument();doc.setDocumentMargin(0);doc.setDefaultFont(self.list.font());doc.setPlainText(row['text'])
        doc.setTextWidth(max(150,self.width()-82))
        if doc.size().height()<=116:
            full=QLabel();full.setTextFormat(Qt.PlainText);full.setWordWrap(True);full.setText(row['text'])
            full.setTextInteractionFlags(Qt.TextSelectableByMouse);full.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred)
            full.setMinimumHeight(max(25,round(doc.size().height())+4))
        else:
            full=QPlainTextEdit();full.setReadOnly(True);full.setPlainText(row['text']);full.setFixedHeight(128)
            full.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        full.setAccessibleName('闪念全文');box.addWidget(full)
        actions=QHBoxLayout();actions.setSpacing(3)
        if row['deleted']:
            actions.addWidget(tool('check','恢复闪念',lambda:self.service.modify(identity,deleted=False),ink,'恢复'));actions.addStretch()
        else:
            done='撤销完成' if row['done'] else '完成'
            actions.addWidget(tool('check',done,lambda:self.service.modify(identity,done=not row['done']),ink,done))
            remind=tool('bell','设置提醒',lambda:self.remind(identity,remind),ink);actions.addWidget(remind)
            pin=tool('pin','取消置顶' if row['pinned'] else '置顶',lambda:self.service.modify(identity,pinned=not row['pinned']),ink)
            pin.setCheckable(True);pin.setChecked(row['pinned']);actions.addWidget(pin)
            actions.addWidget(tool('edit','编辑闪念',lambda:self.begin_edit(identity),ink))
            recolor=QToolButton();recolor.setText('改色');recolor.setAccessibleName('修改本条颜色')
            recolor.clicked.connect(lambda:self.recolor(identity,recolor));actions.addWidget(recolor)
            actions.addStretch()
        actions.addWidget(tool('copy','复制全文',lambda:self.copy_text(row['text']),ink))
        if not row['deleted']:
            actions.addWidget(tool('trash','移入回收站',lambda:self.service.modify(identity,deleted=True),ink))
        box.addLayout(actions)
        return frame

    def copy_text(self,text):
        QApplication.clipboard().setText(text);self.message('已复制全文')
    def recolor(self,identity,anchor):
        color=self.color_choice(anchor)
        if color:self.service.modify(identity,color=color)
    def remind(self,identity,anchor):
        choice=self.menu_choice(anchor,[('short','10 分钟后',None),('hour','1 小时后',None),
                                       ('tomorrow','明天 09:00',None),('choose','指定日期与时间…',None),('clear','取消提醒',None)])
        if not choice:return
        now=dt.datetime.now()
        if choice=='choose':
            self.hold=True;self.fold.stop()
            try:stamp=ask_time(self)
            finally:self.hold=False;self.arm_fold()
            if stamp is None:return
        elif choice=='clear':stamp=0
        else:
            target=(now+dt.timedelta(days=1)).replace(hour=9,minute=0,second=0,microsecond=0) if choice=='tomorrow' else now+dt.timedelta(minutes=10 if choice=='short' else 60)
            stamp=int(target.timestamp())
        if stamp and stamp<=int(now.timestamp()):self.message('请选择将来的提醒时间。');return
        self.service.modify(identity,due=stamp,notified=False)

    def confirm_empty(self):
        self.hold=True;self.fold.stop()
        try:
            count=sum(row['deleted'] for row in self.service.cfg['flash_entries'])
            answer=QMessageBox.question(self,'清空回收站',f'永久删除回收站中的 {count} 条闪念？',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
            if answer==QMessageBox.Yes:self.service.empty_trash()
        finally:self.hold=False;self.arm_fold()

    def draft(self):
        return dict(id=self.edit_id,text=self.editor.toPlainText(),color=self.edit_color)
    def begin_edit(self,identity=''):
        self.fold.stop()
        saved=self.draft() if self.editing else self.service.cfg['flash_draft']
        if saved and identity and saved.get('id')!=identity and saved.get('text','').strip():
            self.message('请先保存或放弃当前草稿。');return
        if identity and (not saved or saved.get('id')!=identity):
            row=self.service.item(identity)
            if not row or row['deleted']:return
            saved=dict(id=identity,text=row['text'],color=row['color'])
        if not saved:saved=dict(id='',text='',color=self.color_filter or self.service.cfg['flash_color'])
        self.tools_timer.stop();self.hide_notice();self.toolbar.hide();self.launch_shell.hide();self.editing=False;self.edit_id=saved['id'];self.edit_color=saved['color']
        self.editor.setPlainText(saved['text']);self.editing=True;self.browse.hide();self.composer.show();self.editor.fit_text();self.reflow()
        self.update_draft_color();self.editor.setFocus(Qt.OtherFocusReason)
        cursor=self.editor.textCursor();cursor.movePosition(cursor.End);self.editor.setTextCursor(cursor)
    def choose_draft_color(self):
        key=self.color_choice(self.color_button)
        if key:self.edit_color=key;self.update_draft_color();self.draft_changed()
    def update_draft_color(self):
        self.color_button.setText(COLORS[self.edit_color][0])
        self.color_button.setIcon(color_icon(self.edit_color))
    def draft_changed(self):
        if self.editing:self.draft_timer.start()
    def load_saved_draft(self):
        if self.editing:
            self.finish_edit()
            if self.service.cfg['flash_draft']:self.begin_edit()
    def finish_edit(self):
        self.draft_timer.stop();self.editing=False;self.edit_id=''
        self.composer.hide();self.editor.clear();self.browse.show();self.reflow()
    def discard(self):
        if self.service.persist(flash_draft={}):
            self.finish_edit();self.render();self.arm_fold()
    def submit(self):
        text=self.editor.toPlainText()
        if not text.strip() or len(text)>MAX_TEXT:
            self.message('先写下想法。' if not text.strip() else f'请将超过 {MAX_TEXT} 字的内容分条保存。');return
        key=self.edit_id
        updating=bool(key and self.service.item(key) and not self.service.item(key)['deleted'])
        if updating:
            ok=self.service.modify(key,clear_draft=True,text=text.strip(),color=self.edit_color)
        else:
            key=self.service.add(text,self.edit_color,clear_draft=True);ok=bool(key)
        if ok:
            self.reveal_item(key,expanded=updating);self.message('已保存闪念');self.arm_fold()

    def arm_fold(self):
        if (not self.editing and not self.hold and self.service.cfg['flash_auto_hide']
                and self.isVisible()):self.fold.start(1000*self.service.cfg['flash_delay'])
    def fold_if_idle(self):
        if (self.editing or self.hold or self.search.hasFocus() and self.search.text()
                or QApplication.activePopupWidget() or QApplication.activeModalWidget()):return
        point=QCursor.pos();edge=self.service.edge
        if not self.mask().contains(self.mapFromGlobal(point)) and not (edge and edge.geometry().contains(point)):
            self.service.collapse()
    def enterEvent(self,event):
        self.fold.stop()
        if not self.toolbar.isVisible() and not self.editing:self.launch_shell.show();self.input_region_later()
        super().enterEvent(event)
    def leaveEvent(self,event):
        self.tools_timer.start();self.arm_fold();super().leaveEvent(event)
    def keyPressEvent(self,event):
        if event.key()==Qt.Key_Escape:
            if self.editing:
                if self.service.save_draft():self.finish_edit();self.render();self.arm_fold()
            elif self.search.isVisible():self.search.clear();self.search.hide();self.reflow()
            else:self.service.collapse()
            event.accept();return
        super().keyPressEvent(event)
    def dragEnterEvent(self,event):
        if self.service.cfg['flash_drop'] and plain_drop(event.mimeData()) and event.possibleActions()&Qt.CopyAction:
            self.fold.stop();copy_drop(event)
        else:event.ignore()
    def dropEvent(self,event):
        if self.service.cfg['flash_drop'] and event.possibleActions()&Qt.CopyAction:
            key=self.service.add(plain_drop(event.mimeData()),self.color_filter or None)
            if key:
                self.reveal_item(key,expanded=False);self.message('拖入文字已保存');copy_drop(event);return
        event.ignore()
    def closeEvent(self,event):
        event.ignore();self.service.collapse()
    def dismiss(self):
        self.fold.stop();self.draft_timer.stop();self.pulse.stop();self.tools_timer.stop();self.notice_timer.stop();self.mask_timer.stop();self.hide();self.deleteLater()


class ReminderToast(QFrame):
    def __init__(self,service,row,count):
        super().__init__(None,TOOL_FLAGS|Qt.WindowDoesNotAcceptFocus)
        self.service=service;self.setAttribute(Qt.WA_ShowWithoutActivating);self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle('闪念提醒');self.setObjectName('FlashReminder')
        c=palette_for(service)
        self.setStyleSheet('QFrame#FlashReminder{background:%s;border:1px solid %s;} QLabel{color:%s;background:transparent;}'%(c['surface'],c['line'],c['ink']))
        layout=QVBoxLayout(self);layout.setContentsMargins(14,10,14,10)
        layout.addWidget(QLabel('闪念提醒' if count==1 else f'{count} 条闪念到期'))
        snippet=QLabel(' '.join(row['text'].split())[:90]);snippet.setTextFormat(Qt.PlainText);snippet.setWordWrap(True);layout.addWidget(snippet)
        button=QPushButton('查看闪念');button.clicked.connect(lambda:(self.close(),service.open(identity=row['id'])));layout.addWidget(button)
        self.setFixedWidth(280);self.adjustSize()
        edge=service.edge
        area=edge.work_area if edge is not None and hasattr(edge,'work_area') else QApplication.primaryScreen().availableGeometry()
        self.move(area.right()-self.width()-10,area.bottom()-self.height()-10)
        self.timeout=QTimer(self);self.timeout.setSingleShot(True);self.timeout.timeout.connect(self.close);self.timeout.start(10000)
    def closeEvent(self,event):
        self.timeout.stop()
        if self.service.toast is self:self.service.toast=None
        super().closeEvent(event)
