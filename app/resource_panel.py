"""Movable monitor panel. Compact and expanded states share one header-centre anchor."""
import ctypes as C
from ctypes import wintypes as W
import os
import time
from PyQt5.QtCore import Qt,QRect,QRectF,QPoint,QPointF,QSize,QTimer
from PyQt5.QtGui import QColor,QPainter,QPainterPath,QPen,QFont,QCursor,QPixmap
from PyQt5.QtWidgets import (QWidget,QLabel,QToolButton,QFrame,QScrollArea,
    QVBoxLayout,QHBoxLayout,QGridLayout,QFormLayout,QLayout,QApplication,QSizePolicy,QBoxLayout)
from ui_style import AlignedMenu
from screen_layout import screen_records,valid_record,capture,project
from fold_options import geometry as fold_geometry
from resource_options import METRICS,background
from flash_view import palette_for,icon


from resource_charts import MetricDisplay,rate,metric_colors
from capsule_glass import CapsuleGlass


def display_values(service):
    cfg=service.cfg;data=service.latest;rows=[]
    for key in ('cpu','memory','network','gpu','fps','cpu_temp','gpu_temp','cpu_power','gpu_power'):
        if not cfg['resource_'+key]:continue
        if key=='gpu' and service.compact:continue
        value=data.get(key);label=METRICS[key];tip='';display='—'
        if key in ('cpu','gpu') and value is not None:display=f'{value:.0f}%'
        elif key=='memory' and value:
            display=f'{value[0]:.0f}%';tip=f'{value[1]/2**30:.1f} / {value[2]/2**30:.1f} GB'
        elif key=='network' and value:display='↓ '+rate(value[0])+'   ↑ '+rate(value[1])
        elif key=='fps' and service.fps:
            display='—' if service.fps.value is None else f'{service.fps.value:.0f}';tip=service.fps.name
        elif key.endswith(('_temp','_power')):
            reading=service.sensors.values.get(key) if service.sensors else None
            if reading:
                label=reading['label'];tip=reading['source'];display=('%g °C' if key.endswith('_temp') else '%g W')%reading['value']
            else:tip='当前传感器未提供读数'
        if key=='gpu':tip='所有显卡中最忙引擎的利用率' if value is not None else '等待显卡驱动计数器'
        rows.append((key,label,display,tip))
    return rows


class BatteryRows(QWidget):
    def __init__(self,window):
        super().__init__()
        self.owner_window=window
        self.legend=[]
        self.status=''
        self.name_width=0
        self.setFixedHeight(62)

    def refresh(self,gauge):
        self.legend=gauge.group() if gauge else []
        self.status=gauge.status if gauge else '正在读取蓝牙设备…'
        summary='\\n'.join(row['name']+' · '+self.percentage(row) for row in self.legend) or self.status
        self.setToolTip(summary);self.setAccessibleName(summary);self.update()

    @staticmethod
    def percentage(row):
        return '未报告' if row['level'] is None else f"{row['level']}%"

    def paintEvent(self,event):
        from bluetooth_gauge import draw_rings
        p=QPainter(self);p.setRenderHints(QPainter.Antialiasing|QPainter.TextAntialiasing)
        c=self.owner_window.colors
        draw_rings(p,QRectF(1,3,54,54),self.legend,not c['light'])
        font=QFont(self.font());font.setPixelSize(12);p.setFont(font)
        if not self.legend:
            p.setPen(QColor(c['muted']))
            p.drawText(QRect(63,0,max(1,self.width()-64),60),Qt.AlignVCenter|Qt.TextWordWrap,self.status)
            return
        metrics=p.fontMetrics();value_font=QFont(font);value_font.setWeight(QFont.DemiBold)
        name_x=72;gap=8
        # These three columns are sized by their contents. Enlarging the window never separates a reading from its ring.
        from PyQt5.QtGui import QFontMetrics
        numbers=QFontMetrics(value_font)
        value_width=max(numbers.horizontalAdvance(self.percentage(row)) for row in self.legend)+2
        self.name_width=max(1,min(112,self.width()-name_x-gap-value_width-2,
                                  max(metrics.horizontalAdvance(row['name']) for row in self.legend)))
        self.value_x=name_x+self.name_width+gap
        first=(self.height()-19*len(self.legend))//2
        for i,row in enumerate(self.legend):
            y=first+19*i
            p.setPen(Qt.NoPen);p.setBrush(QColor(row['ink']));p.drawEllipse(QPointF(64,y+9),3,3)
            p.setPen(QColor(c['ink']));p.setFont(font)
            p.drawText(QRect(name_x,y,self.name_width+1,19),Qt.AlignVCenter,metrics.elidedText(row['name'],Qt.ElideRight,self.name_width+1))
            p.setFont(value_font);p.drawText(QRect(self.value_x,y,value_width,19),Qt.AlignRight|Qt.AlignVCenter,self.percentage(row))


class ResourceWindow(QWidget):
    def __init__(self,service):
        super().__init__(None,Qt.Tool|Qt.FramelessWindowHint|Qt.NoDropShadowWindowHint)
        self.service=service;self.press=None;self.offset=0;self.rank_by='cpu';self.last_layer=None
        self.setAttribute(Qt.WA_TranslucentBackground);self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle('资源胶囊 · 大肥鱼Dock');self.setAccessibleName('系统资源监控')
        self.detail=QWidget(self);lay=QVBoxLayout(self.detail);lay.setContentsMargins(12,0,12,10);lay.setSpacing(2)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);lay.addWidget(self.scroll)
        page=QWidget();self.scroll.setWidget(page);body=QVBoxLayout(page);body.setContentsMargins(2,2,4,1);body.setSpacing(7);body.setSizeConstraint(QLayout.SetMinAndMaxSize);self.body=body;self.page=page
        self.glass=CapsuleGlass()
        self.dashboard=QWidget()
        self.columns=QBoxLayout(QBoxLayout.LeftToRight,self.dashboard)
        self.columns.setContentsMargins(0,0,0,0);self.columns.setSpacing(18)
        self.graph=MetricDisplay(self)
        self.columns.addWidget(self.graph,3,Qt.AlignTop)
        self.rank_section=QWidget()
        rank_body=QVBoxLayout(self.rank_section)
        rank_body.setContentsMargins(0,0,0,0);rank_body.setSpacing(3)
        self.rank_head=QWidget();head=QHBoxLayout(self.rank_head)
        head.setContentsMargins(0,0,0,0);head.setSpacing(3)
        title=QLabel('进程排行');title.setObjectName('RankTitle');head.addWidget(title,1)
        self.rank_buttons={}
        for key,heading in [('cpu','CPU'),('memory','内存')]:
            control=QToolButton();control.setText(heading);control.setCheckable(True)
            control.setAccessibleName('按'+heading+'排序');control.setToolTip('按'+heading+'占用排序')
            control.clicked.connect(lambda checked=False,key=key:self.select_sort(key))
            control.setObjectName('RankSort');head.addWidget(control);self.rank_buttons[key]=control
        rank_body.addWidget(self.rank_head)
        self.rank_widget=QWidget()
        grid=QGridLayout(self.rank_widget);grid.setContentsMargins(0,0,0,0)
        grid.setHorizontalSpacing(6);grid.setVerticalSpacing(2);grid.setColumnStretch(1,1)
        self.rank_labels=[];self.rank_icons={};self.rank_frame=None;self.rank_style=None
        for i in range(5):
            mark=QLabel();mark.setFixedSize(15,15);mark.setAlignment(Qt.AlignCenter)
            name=QLabel();name.setTextFormat(Qt.PlainText);name.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred)
            cpu=QLabel();ram=QLabel();ram.setObjectName('RankMemory')
            for field in (cpu,ram):field.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
            for col,field in enumerate((mark,name,cpu,ram)):grid.addWidget(field,i,col)
            self.rank_labels.append((mark,name,cpu,ram))
        rank_body.addWidget(self.rank_widget);rank_body.addStretch(1)
        self.side_section=QWidget()
        self.side_layout=QVBoxLayout(self.side_section)
        self.side_layout.setContentsMargins(0,0,0,0);self.side_layout.setSpacing(8)
        self.side_layout.addWidget(self.rank_section)
        self.columns.addWidget(self.side_section,2,Qt.AlignTop)
        body.addWidget(self.dashboard)
        self.no_readings=QLabel('在「设置」中选择要显示的读数。');self.no_readings.setWordWrap(True);body.addWidget(self.no_readings)
        self.bt_head=QWidget();row=QHBoxLayout(self.bt_head);row.setContentsMargins(0,0,0,0)
        row.setSpacing(5);row.addWidget(QLabel('蓝牙电量'));self.bt_page=QToolButton();self.bt_page.clicked.connect(self.next_devices);row.addWidget(self.bt_page)
        self.bt_refresh=QToolButton();self.bt_refresh.setText('刷新');self.bt_refresh.clicked.connect(self.refresh_bt);row.addWidget(self.bt_refresh)
        row.addStretch()
        self.battery_section=QWidget();battery_layout=QVBoxLayout(self.battery_section)
        battery_layout.setContentsMargins(0,0,0,0);battery_layout.setSpacing(0)
        battery_layout.addWidget(self.bt_head);self.rings=BatteryRows(self);battery_layout.addWidget(self.rings)
        self.side_layout.addWidget(self.battery_section);body.addStretch()
        self.settings_button=QToolButton(self);self.settings_button.setAccessibleName('资源胶囊设置');self.settings_button.setToolTip('资源胶囊设置');self.settings_button.clicked.connect(service.settings)
        self.fold_button=QToolButton(self);self.fold_button.setAccessibleName('收起胶囊');self.fold_button.setToolTip('收起胶囊');self.fold_button.clicked.connect(lambda:service.fold(True))
        self.leave_timer=QTimer(self);self.leave_timer.setSingleShot(True);self.leave_timer.timeout.connect(self.fold_idle)
        self.enter_timer=QTimer(self);self.enter_timer.setSingleShot(True);self.enter_timer.setInterval(230);self.enter_timer.timeout.connect(self.expand_hover)
        self.colors={}

    def sync_window(self):
        cfg=self.service.cfg;self.background=background(cfg);colors=palette_for(self.service,self.background)
        if colors!=self.colors:
            self.colors=colors
            self.setStyleSheet("""
                QWidget{background:transparent;color:%(ink)s}
                QLabel{font-size:12px}
                QLabel#RankTitle{font-weight:600}
                QLabel#RankMemory{color:%(muted)s}
                QToolButton{border:0;border-radius:6px;padding:3px 5px;color:%(muted)s;background:transparent}
                QToolButton:hover,QToolButton:checked{background:%(hover)s;color:%(ink)s}
                QToolButton#RankSort{font-size:10px;padding:2px 5px}
                QScrollArea{border:0}
            """ % colors)
            self.settings_button.setIcon(icon('settings',colors['ink']));self.fold_button.setIcon(icon('collapse',colors['ink']))
            for btn in (self.settings_button,self.fold_button):btn.setIconSize(QSize(15,15))
        compact=self.service.compact;self.detail.setVisible(not compact)
        self.settings_button.setVisible(not compact);self.fold_button.setVisible(not compact)
        if compact or not cfg['resource_rank']:
            self.rank_icons.clear();self.rank_frame=self.rank_style=None
            for mark,*_ in self.rank_labels:mark.clear()
        if not cfg['resource_auto_hide']:self.leave_timer.stop();self.enter_timer.stop()
        self.reposition();self.refresh()

    def desktop_rect(self):
        screens=screen_records()
        if not screens:return QRect(0,0,680,202)
        record=valid_record(self.service.cfg['resource_layout'])
        rect=project(record,screens,minimum=(220,90)) if record else None
        if rect:return QRect(*rect)
        x,y,w,h=screens[0]['area']
        cfg=self.service.cfg
        extras=sum(cfg['resource_'+key] for key in ('fps','cpu_temp','gpu_temp','cpu_power','gpu_power'))
        chart_height=82*bool(cfg['resource_cpu'] or cfg['resource_gpu'])+31*cfg['resource_memory']+27*cfg['resource_network']+25*((extras+1)//2)
        side_height=112*cfg['resource_rank']+82*cfg['resource_bluetooth']+8*bool(cfg['resource_rank'] and cfg['resource_bluetooth'])
        width=min(w,680 if chart_height and side_height else 380 if chart_height else 280)
        content=max(chart_height,side_height) if width>=500 or not (chart_height and side_height) else chart_height+side_height+8
        height=min(h,max(92,content+55))
        return QRect(x+(w-width)//2,y+min(18,max(0,h-height)),width,height)

    def reposition(self):
        if self.press is not None:return
        cfg=self.service.cfg;rect=self.desktop_rect();compact=self.service.compact
        if compact:
            kind=cfg['resource_fold']
            rect=QRect(*fold_geometry(list(rect.getRect()),{'style':'capsule' if kind=='pill' else kind,'ratio':80},38))
            if kind=='pill' and rect.width()>300:
                center=rect.center();rect.setWidth(300);rect.moveCenter(center)
        if self.geometry()!=rect:self.setGeometry(rect)
        self.show();self.layer()
    def taskbar_at(self,point):
        if self.service.runtime.dock.preview:return None
        from resource_taskbar import taskbars
        return next((bar for bar in taskbars() if bar['rect'].contains(point)),None)

    def layer(self):
        target=0;mode=self.service.cfg['resource_layer']
        state=(mode,target)
        if self.last_layer==state or self.service.runtime.dock.preview:return
        self.last_layer=state
        user=C.windll.user32;user.GetShellWindow.restype=W.HWND
        user.SetWindowLongPtrW.argtypes=[W.HWND,C.c_int,C.c_ssize_t];user.SetWindowLongPtrW.restype=C.c_ssize_t
        user.SetWindowPos.argtypes=[W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT]
        window=int(self.winId());owner=target if target else (user.GetShellWindow() or 0) if mode=='bottom' else 0
        user.SetWindowLongPtrW(window,-8,owner)
        if mode=='bottom':user.SetWindowPos(window,-2,0,0,0,0,0x13)
        user.SetWindowPos(window,1 if mode=='bottom' else -1,0,0,0,0,0x13)
    def raise_if_top(self):
        if self.service.cfg['resource_layer']=='top':self.raise_()
    def select_sort(self,key):
        self.rank_by=key
        self.refresh()

    def show_ranking(self):
        frame=self.service.latest.get('rank');style=(self.rank_by,self.devicePixelRatioF(),self.colors['ink'],self.colors['hover'])
        if self.rank_style==style and self.rank_frame is frame:return
        self.rank_frame=frame;self.rank_style=style
        for key,btn in self.rank_buttons.items():btn.setChecked(key==self.rank_by)
        data=frame or {}
        ranked=data.get(self.rank_by,[])
        paths=data.get('paths',{})
        icons={}
        for i,(mark,name,cpu,ram) in enumerate(self.rank_labels):
            for field in (mark,name,cpu,ram):field.setVisible(i<len(ranked))
            if i>=len(ranked):
                mark.clear()
                if not ranked and i==0:name.show();name.setText('等待读数…');name.setToolTip('')
                continue
            app,pid,percent,memory=ranked[i]
            name.setText(app)
            detail=data.get('members',{}).get(pid,())
            description='\\n'.join(f'{n} · PID {p} · {mem/2**20:.1f} MB' for n,p,_,mem in detail)
            name.setToolTip(description or f'{app} · PID {pid}')
            ram.setToolTip('专用工作集'+('\\n'+description if description else ''))
            cpu.setText('—' if percent is None else f'{percent:.1f}%')
            ram.setText('—' if memory is None else f'{memory/2**30:.1f} GB' if memory>=2**30 else f'{memory/2**20:.1f} MB')
            path=paths.get(pid,'')
            # Shell icons are resolved only for local, visible entries and kept only for this ranking.
            if len(path)>2 and path[1]==':' and path.lower().endswith('.exe'):
                cache_key=(path,mark.devicePixelRatioF())
                pixmap=self.rank_icons.get(cache_key)
                if pixmap is None:
                    api=self.service.runtime.api;size=max(15,round(15*cache_key[1]))
                    handle=api.extract_hicon(path,size)
                    image=api.hicon_to_qimage(handle) if handle else None
                    pixmap=QPixmap.fromImage(image) if image is not None else QPixmap()
                    pixmap.setDevicePixelRatio(cache_key[1])
                icons[cache_key]=pixmap
                if not pixmap.isNull():
                    mark.setStyleSheet('');mark.setPixmap(pixmap);continue
            mark.setText(app[:1].upper())
            mark.setStyleSheet('border-radius:4px;font-weight:600;font-size:10px;color:%s;background:%s;'%(self.colors['ink'],self.colors['hover']))
        self.rank_icons=icons

    def next_devices(self):
        if self.service.bluetooth:self.service.bluetooth.turn(1)
    def refresh_bt(self):
        if self.service.bluetooth:self.service.bluetooth.refresh()
    def refresh(self):
        cfg=self.service.cfg;self.values=display_values(self.service)
        self.setToolTip('\n'.join(label+'  '+value+(' · '+tip if tip else '') for _,label,value,tip in self.values) or '资源胶囊 · 点击展开')
        if not self.service.compact:
            self.graph.refresh(self.values)
            self.no_readings.setVisible(not self.values and not (cfg['resource_rank'] or cfg['resource_bluetooth']))
            self.rank_section.setVisible(cfg['resource_rank'])
            self.side_section.setVisible(cfg['resource_rank'] or cfg['resource_bluetooth'])
            self.battery_section.setVisible(cfg['resource_bluetooth'])
            self.dashboard.setVisible(bool(self.values) or cfg['resource_rank'] or cfg['resource_bluetooth'])
            if cfg['resource_rank']:self.show_ranking()
            self.bt_head.setVisible(cfg['resource_bluetooth']);self.rings.setVisible(cfg['resource_bluetooth'])
            bt=self.service.bluetooth;self.bt_page.setVisible(bool(bt and bt.pages()>1))
            if bt:self.bt_page.setText(f'{bt.page+1}/{bt.pages()} ›')
            if cfg['resource_bluetooth']:self.rings.refresh(bt)
            self.body.activate()
            wanted=self.body.minimumSize().height()
            if self.page.minimumHeight()!=wanted:self.page.setMinimumHeight(wanted)
        self.update()

    def resizeEvent(self,event):
        h=min(38,self.height());self.detail.setGeometry(0,h,self.width(),max(1,self.height()-h))
        self.columns.setDirection(QBoxLayout.LeftToRight if self.width()>=500 else QBoxLayout.TopToBottom)
        self.columns.setSpacing(18 if self.width()>=500 else 8)
        self.fold_button.setGeometry(self.width()-35,5,26,26);self.settings_button.setGeometry(self.width()-64,5,26,26)
        super().resizeEvent(event)
    def paintEvent(self,event):
        if not self.colors:return
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);p.setRenderHint(QPainter.TextAntialiasing)
        cfg=self.service.cfg;c=self.colors;compact=self.service.compact;rect=QRectF(self.rect()).adjusted(1,1,-1,-1)
        radius=min(17,rect.height()/2)
        if compact and cfg['resource_fold']=='bar':radius=min(12,rect.height()/2)
        self.glass.paint(p,self,self,radius,self.press is not None,self.background)
        ink=QColor(c['ink']);accent=QColor(metric_colors(self.service)['cpu']);font=QFont(self.font());font.setPixelSize(13)
        if compact and (self.width()<70 or (cfg['resource_fold']=='ball')):
            q=rect.center();p.setPen(QPen(accent,2,Qt.SolidLine,Qt.RoundCap))
            for n,h in enumerate((7,14,10)):p.drawLine(QPointF(q.x()-5+5*n,q.y()+6),QPointF(q.x()-5+5*n,q.y()+6-h))
            return
        if not compact:
            p.setPen(QPen(accent,2,Qt.SolidLine,Qt.RoundCap))
            for n,h in enumerate((6,13,9)):p.drawLine(16+n*4,24,16+n*4,24-h)
            font.setWeight(QFont.DemiBold);font.setPixelSize(15);p.setFont(font);p.setPen(ink)
            p.drawText(QRect(34,0,self.width()-124,38),Qt.AlignVCenter,'系统资源')
            if self.width()>=430 and self.service.history:
                stamp=self.service.history[-1]['time']
                sampled_at=time.time()-max(0,time.monotonic()-stamp)
                font.setPixelSize(11);font.setWeight(QFont.Normal);p.setFont(font);p.setPen(QColor(c['muted']))
                p.drawText(QRect(self.width()//2-30,0,60,38),Qt.AlignCenter,time.strftime('%H:%M',time.localtime(sampled_at)))
            return
        p.setFont(font);p.setPen(ink)
        bt=self.service.bluetooth if cfg['resource_bluetooth'] else None
        right=self.width()-11
        if bt:
            from bluetooth_gauge import draw_rings
            edge=min(26,self.height()-8);draw_rings(p,QRectF(right-edge,(self.height()-edge)/2,edge,edge),bt.group(),not c['light']);right-=edge+6
        labels=[(v.replace(' KB/s','K').replace(' MB/s','M').replace(' B/s','B') if key=='network' else label+' '+v)
                for key,label,v,_ in getattr(self,'values',[])]
        if labels:
            start=self.offset%len(labels);labels=labels[start:]+labels[:start]
        available=max(1,right-12);shown=[]
        for i,label in enumerate(labels):
            text='   '.join(shown+[label]);remaining=len(labels)-i-1
            suffix=('  +'+str(remaining)) if remaining else ''
            if shown and p.fontMetrics().horizontalAdvance(text+suffix)>available:break
            shown.append(label)
        text='   '.join(shown)
        if len(shown)<len(labels):text+='  +'+str(len(labels)-len(shown))
        if not text:text=str(len(bt.rows))+' 台蓝牙设备' if bt else '资源胶囊'
        p.setPen(ink);p.setFont(font);p.drawText(QRect(12,0,available,self.height()),Qt.AlignVCenter,p.fontMetrics().elidedText(text,Qt.ElideRight,available))

    def wheelEvent(self,event):
        if self.service.compact and event.angleDelta().y():
            self.offset+=1 if event.angleDelta().y()<0 else -1;self.update();event.accept()
        else:event.ignore()
    def enterEvent(self,event):
        self.leave_timer.stop()
        if self.service.cfg['resource_auto_hide'] and self.service.compact:self.enter_timer.start()
        super().enterEvent(event)
    def expand_hover(self):
        if self.press is None and self.isVisible() and self.geometry().contains(QCursor.pos()):self.service.fold(False,automatic=True)
    def leaveEvent(self,event):
        self.enter_timer.stop()
        if self.service.cfg['resource_auto_hide'] and not self.service.compact:
            self.leave_timer.start(1000*self.service.cfg['resource_delay'])
        super().leaveEvent(event)
    def fold_idle(self):
        if self.press is None and not self.geometry().contains(QCursor.pos()) and not QApplication.activePopupWidget() and not QApplication.activeModalWidget():
            self.service.fold(True,automatic=True)
    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton and (event.y()<38 or self.service.compact):
            self.enter_timer.stop();self.leave_timer.stop();self.press=event.globalPos();self.origin=self.pos()
            self.original=self.desktop_rect();self.moved=False;event.accept()
        else:super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if self.press is None:return
        delta=event.globalPos()-self.press
        if delta.manhattanLength()>=QApplication.startDragDistance():self.moved=True
        if self.moved:self.move(self.origin+delta)
    def mouseReleaseEvent(self,event):
        if event.button()!=Qt.LeftButton or self.press is None:return
        self.press=None
        if not self.moved:
            if self.service.compact:self.service.fold(False)
            return
        bar=self.taskbar_at(event.globalPos())
        if bar:
            self.reposition();self.service.offer_taskbar(bar,event.globalPos());return
        rect=QRect(self.original);rect.moveTopLeft(QPoint(self.geometry().center().x()-rect.width()//2,self.y()))
        screen=QApplication.screenAt(event.globalPos()) or QApplication.primaryScreen();area=screen.availableGeometry()
        rect.moveLeft(max(area.left(),min(rect.x(),area.right()-rect.width()+1)))
        rect.moveTop(max(area.top(),min(rect.y(),area.bottom()-rect.height()+1)))
        if not self.service.set_options(resource_layout=capture(list(rect.getRect()),screen_records())):self.reposition()
    def contextMenuEvent(self,event):
        self.enter_timer.stop();self.leave_timer.stop();menu=AlignedMenu(self);cfg=self.service.cfg
        menu.addAction('展开详情' if self.service.compact else '收起胶囊',lambda:self.service.fold(not self.service.compact))
        for name,layer in [('置顶显示','top'),('置于底层','bottom')]:
            item=menu.addAction(name);item.setCheckable(True);item.setChecked(cfg['resource_layer']==layer)
            item.triggered.connect(lambda checked,layer=layer:self.service.set_options(resource_layer=layer))
        bar=menu.addAction('任务栏监控');bar.setCheckable(True);bar.setChecked(cfg['resource_taskbar'])
        bar.triggered.connect(lambda enabled:self.service.set_options(resource_taskbar=enabled))
        auto=menu.addAction('鼠标离开自动收起');auto.setCheckable(True);auto.setChecked(cfg['resource_auto_hide'])
        auto.triggered.connect(lambda on:self.service.set_options(resource_auto_hide=on))
        menu.addSeparator();menu.addAction('资源显示设置…',self.service.settings)
        menu.addAction('关闭资源胶囊',lambda:self.service.set_options(resource_enabled=False))
        try:menu.exec_(event.globalPos())
        finally:menu.deleteLater()
    def closeEvent(self,event):
        event.ignore();self.service.set_options(resource_enabled=False)
    def dispose(self):
        self.enter_timer.stop();self.leave_timer.stop();self.glass.clear();self.hide();self.deleteLater()


from resource_settings import ResourceOptions
