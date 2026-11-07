"""Movable monitor panel. Compact and expanded states share one header-centre anchor."""
import ctypes as C
from ctypes import wintypes as W
import os
import time
from PyQt5.QtCore import Qt,QRect,QRectF,QPoint,QPointF,QSize,QTimer
from PyQt5.QtGui import QColor,QPainter,QPainterPath,QPen,QFont,QCursor,QPixmap
from PyQt5.QtWidgets import (QWidget,QLabel,QToolButton,QFrame,QScrollArea,
    QVBoxLayout,QHBoxLayout,QGridLayout,QFormLayout,QLayout,QApplication,QSizePolicy)
from ui_style import AlignedMenu
from screen_layout import screen_records,valid_record,capture,project
from fold_options import geometry as fold_geometry
from resource_options import METRICS,SENSOR_UNITS,background
from flash_view import palette_for,icon


from resource_charts import MetricDisplay,SensorColumns,rate,metric_colors
from capsule_glass import CapsuleGlass


def display_values(service):
    cfg=service.cfg;data=service.latest;rows=[]
    for key in ('cpu','memory','network','gpu','fps',*SENSOR_UNITS):
        if not cfg['resource_'+key]:continue
        if service.compact and key not in cfg['resource_compact_metrics']:continue
        value=data.get(key);label=METRICS[key];tip='';display='—'
        if key in ('cpu','gpu') and value is not None:display=f'{value:.0f}%'
        elif key=='memory' and value:
            display=f'{value[0]:.0f}%';tip=f'{value[1]/2**30:.1f} / {value[2]/2**30:.1f} GB'
        elif key=='network' and value:display='↓ '+rate(value[0])+'   ↑ '+rate(value[1])
        elif key=='fps' and service.fps:
            display='—' if service.fps.value is None else f'{service.fps.value:.0f}';tip=service.fps.name
        elif key in SENSOR_UNITS:
            reading=service.sensors.values.get(key) if service.sensors else None
            if reading:
                label=reading['label'];tip=reading['source'];display=f"{reading['value']:g} {reading.get('unit',SENSOR_UNITS[key])}"
            else:
                if cfg['resource_hide_unavailable']:continue
                tip='当前传感器未提供读数'
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
        self.page_key='resources';self._displayed_compact=None;self.halo_phase=0.;self.compact_pages=1
        self.setAttribute(Qt.WA_TranslucentBackground);self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle('资源胶囊 · 大肥鱼Dock');self.setAccessibleName('系统资源监控')
        self.detail=QWidget(self);lay=QVBoxLayout(self.detail);lay.setContentsMargins(12,0,12,10);lay.setSpacing(2)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);lay.addWidget(self.scroll)
        self.glass = CapsuleGlass()
        self.dashboard = None
        self.rank_labels = []
        self.rank_icons = {}
        self._ai_view=self._music_view=None
        self._traffic_view=self._weather_view=None
        self._saved_view_state = {}
        self.nav=QScrollArea(self);self.nav.setFrameShape(QFrame.NoFrame)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);self.nav.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav_content=QWidget();self.nav.setWidget(self.nav_content)
        self.nav_arrows=[]
        for title,direction in [('‹',-1),('›',1)]:
            button=QToolButton(self);button.setText(title);button.setAccessibleName('向左切换栏目' if direction<0 else '向右切换栏目')
            button.clicked.connect(lambda checked=False,d=direction:self.nav.horizontalScrollBar().setValue(self.nav.horizontalScrollBar().value()+d*100));self.nav_arrows.append(button)
        self.page_buttons={}
        for key,title in [('resources','资源'),('ai','AI'),('music','音乐'),('traffic','流量'),('weather','天气')]:
            btn=QToolButton(self.nav_content);btn.setText(title);btn.setCheckable(True);btn.clicked.connect(lambda checked=False,key=key:self.select_page(key));self.page_buttons[key]=btn
        self.settings_button=QToolButton(self);self.settings_button.setAccessibleName('资源胶囊设置');self.settings_button.setToolTip('资源胶囊设置');self.settings_button.clicked.connect(service.settings)
        self.fold_button=QToolButton(self);self.fold_button.setAccessibleName('收起胶囊');self.fold_button.setToolTip('收起胶囊');self.fold_button.clicked.connect(lambda:service.fold(True))
        self.outside_since = None
        self.auto_fold_timer = QTimer(self)
        self.auto_fold_timer.setInterval(250)
        self.auto_fold_timer.timeout.connect(self.fold_idle)
        self.enter_timer=QTimer(self);self.enter_timer.setSingleShot(True);self.enter_timer.setInterval(230);self.enter_timer.timeout.connect(self.expand_hover)
        self.colors={}
        self.animation=QTimer(self);self.animation.setInterval(33);self.animation.timeout.connect(self.animate)
        self.clock_tick=QTimer(self);self.clock_tick.setInterval(1000);self.clock_tick.timeout.connect(self.update)
        self.rotate=QTimer(self);self.rotate.setInterval(6000);self.rotate.timeout.connect(self.next_page)
        from resource_resize import ResizeEdges
        self.resize_edges=ResizeEdges(self)
        from resource_liquid import CapsuleMotion
        self.liquid=CapsuleMotion(self)

    def build_dashboard(self):
        page=QWidget();self.scroll.setWidget(page);body=QVBoxLayout(page);body.setContentsMargins(2,2,4,1);body.setSpacing(7);body.setSizeConstraint(QLayout.SetMinAndMaxSize);self.body=body;self.page=page
        self.dashboard=QWidget(page)
        self.columns=QGridLayout(self.dashboard)
        self.columns.setContentsMargins(0,0,0,0)
        self.columns.setHorizontalSpacing(18);self.columns.setVerticalSpacing(8)
        self.columns.setColumnStretch(0,3);self.columns.setColumnStretch(1,2)
        self.dashboard_layout_key = None
        self.graph=MetricDisplay(self)
        self.graph.setParent(self.dashboard)
        self.rank_section=QWidget(self.dashboard)
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
        body.addWidget(self.dashboard)
        self.sensor_columns=SensorColumns(self);self.sensor_columns.setParent(self.dashboard)
        self.no_readings=QLabel('在「设置」中选择要显示的读数。');self.no_readings.setWordWrap(True);body.addWidget(self.no_readings)
        self.bt_head=QWidget();row=QHBoxLayout(self.bt_head);row.setContentsMargins(0,0,0,0)
        row.setSpacing(5);row.addWidget(QLabel('蓝牙电量'));self.bt_page=QToolButton();self.bt_page.clicked.connect(self.next_devices);row.addWidget(self.bt_page)
        self.bt_refresh=QToolButton();self.bt_refresh.setText('刷新');self.bt_refresh.clicked.connect(self.refresh_bt);row.addWidget(self.bt_refresh)
        row.addStretch()
        self.battery_section=QWidget(self.dashboard);battery_layout=QVBoxLayout(self.battery_section)
        battery_layout.setContentsMargins(0,0,0,0);battery_layout.setSpacing(0)
        battery_layout.addWidget(self.bt_head);self.rings=BatteryRows(self);battery_layout.addWidget(self.rings)
        body.addStretch()

    def layout_dashboard(self):
        groups = ((self.graph, self.rank_section), (self.sensor_columns, self.battery_section))
        visible = tuple(tuple(panel for panel in group if not panel.isHidden()) for group in groups)
        wide = self.width() >= 500
        key = (wide, visible)
        if key == self.dashboard_layout_key:
            return
        self.dashboard_layout_key = key
        for group in groups:
            for panel in group:
                self.columns.removeWidget(panel)
        rows = visible if wide else [(panel,) for group in visible for panel in group]
        for row, panels in enumerate(group for group in rows if group):
            span = 2 if len(panels) == 1 else 1
            for column, panel in enumerate(panels):
                self.columns.addWidget(panel, row, column, 1, span, Qt.AlignTop)
        self.dashboard.setVisible(any(visible))

    def release_dashboard(self):
        if self.dashboard is None:
            return
        page = self.scroll.takeWidget()
        self.dashboard = None
        self.rank_labels = []
        self.rank_icons.clear()
        for name in ('columns','graph','rank_section','rank_head','rank_buttons','rank_widget',
                     'dashboard_layout_key','sensor_columns','no_readings','bt_head','bt_page',
                     'bt_refresh','battery_section','rings','body','page'):
            self.__dict__.pop(name, None)
        if page is not None:
            page.deleteLater()

    def select_page(self,key):
        before=self.service.active_keys()
        self.page_key='ai' if key=='stats' else key if key in self.page_buttons else 'resources';self.refresh();self.reposition()
        self.nav.ensureWidgetVisible(self.page_buttons[self.page_key],0,0)
        if before!=self.service.active_keys():self.service.sync()
        elif self.service.deck:self.service.deck.configure()
    def page_enabled(self,key):
        cfg=self.service.cfg
        return True if key=='resources' else cfg['resource_ai'] or cfg['resource_ai_tray'] if key=='ai' else cfg['resource_'+key]
    def view(self,key):
        view=getattr(self,'_'+key+'_view')
        if view is None:
            from resource_pages import AiView,MusicView,InfoPage
            view=(AiView(self) if key=='ai' else MusicView(self) if key=='music' else InfoPage(self,key))
            setattr(self,'_'+key+'_view',view);view.hide();self.detail.layout().addWidget(view)
            state = self._saved_view_state.pop(key, None)
            if state and key == 'ai':
                period, metric, provider = state
                view.statistics.period = period
                view.statistics.metric = metric
                view.statistics.refresh()
                view.statistics.provider.setCurrentIndex(max(0, view.statistics.provider.findData(provider)))
        return view

    def release_inactive_views(self):
        if self.service.compact:
            self.release_dashboard()
        for key in ('ai', 'music', 'traffic', 'weather'):
            name = '_' + key + '_view'
            view = getattr(self, name)
            if view is None or view.isVisible():
                continue
            if key == 'ai':
                statistics = view.statistics
                self._saved_view_state[key] = (statistics.period, statistics.metric, statistics.provider.currentData())
            self.detail.layout().removeWidget(view)
            setattr(self, name, None)
            view.deleteLater()
    @property
    def ai_view(self):return self.view('ai')
    @property
    def music_view(self):return self.view('music')
    @property
    def stats_view(self):return self.ai_view.statistics
    @property
    def traffic(self):return self.view('traffic').content
    @property
    def weather_view(self):return self.view('weather').content
    def animate(self):
        self.halo_phase=(time.monotonic()%12)/12;self.update()
    def next_page(self):
        if self.press is None and not self.underMouse() and self.compact_pages>1:self.offset+=1;self.update()
    def sync_animation(self):
        cfg=self.service.cfg;visible=self.isVisible()
        for timer,active in [(self.animation,visible and cfg['resource_halo'] and cfg.get('motion_enabled',True) and not self.service.runtime.lite),
                             (self.clock_tick,visible and self.service.compact and cfg['resource_clock']),
                             (self.rotate,visible and self.service.compact and cfg['resource_compact_rotate'])]:
            if active and not timer.isActive():timer.start()
            elif not active:timer.stop()

    def sync_auto_fold(self):
        if self.isVisible() and not self.service.compact and self.service.cfg['resource_auto_hide']:
            if not self.auto_fold_timer.isActive():
                self.auto_fold_timer.start()
        else:
            self.auto_fold_timer.stop()
            self.outside_since = None

    def sync_window(self):
        self.liquid.prepare()
        cfg=self.service.cfg;self.background=background(cfg);colors=palette_for(self.service,self.background)
        if colors!=self.colors:
            self.colors=colors
            from resource_pages import SCROLL_STYLE
            self.setStyleSheet("""
                QWidget{background:transparent;color:%(ink)s}
                QLabel{font-size:10px}
                QLabel#RankTitle{font-weight:600}
                QLabel#RankMemory{color:%(muted)s}
                QLabel#Subtle{color:%(muted)s;font-size:10px}
                QToolButton{border:0;border-radius:5px;padding:2px 5px;color:%(muted)s;background:transparent;font-size:10px}
                QToolButton:hover,QToolButton:checked{background:%(hover)s;color:%(ink)s}
                QToolButton#RankSort{font-size:10px;padding:2px 5px}
                QScrollArea{border:0}
                QTableWidget{background:transparent;border:0;selection-background-color:%(hover)s;color:%(ink)s;font-size:12px}
                QHeaderView::section{background:%(hover)s;color:%(muted)s;border:0;padding:5px;font-size:11px}
                QTableCornerButton::section{background:%(hover)s;border:0}
                QDateEdit{background:%(hover)s;color:%(ink)s;border:0;border-radius:5px;padding:4px}
                QSlider::groove:horizontal{background:%(hover)s;height:4px;border:0;border-radius:2px}
                QSlider::sub-page:horizontal{background:%(muted)s;border-radius:2px}
                QSlider::handle:horizontal{background:%(ink)s;width:12px;margin:-4px 0;border-radius:6px}
            """ % colors+SCROLL_STYLE)
            self.settings_button.setIcon(icon('settings',colors['ink']));self.fold_button.setIcon(icon('collapse',colors['ink']))
            for btn in (self.settings_button,self.fold_button):btn.setIconSize(QSize(15,15))
        compact = self.service.compact
        opening = False
        # Temporarily folding the card while settings are open is not a new visit.
        if not self.service.editing or self.service.preview_detail:
            opening = not compact and self._displayed_compact is not False
            self._displayed_compact = compact
            preferred = cfg['resource_open_page']
            if opening and preferred != 'last':
                self.page_key = preferred if self.page_enabled(preferred) else 'resources'
        self.detail.setVisible(not compact)
        self.settings_button.setVisible(not compact);self.fold_button.setVisible(not compact)
        if compact or not cfg['resource_rank']:
            self.rank_icons.clear();self.rank_frame=self.rank_style=None
            for mark,*_ in self.rank_labels:mark.clear()
        if cfg['resource_expand_mode']!='hover':self.enter_timer.stop()
        self.reposition();self.refresh();self.sync_animation()
        self.sync_auto_fold()
        if opening:
            self.nav.ensureWidgetVisible(self.page_buttons[self.page_key], 0, 0)
        self.resize_edges.sync()
        self.liquid.sync()

    def desktop_rect(self, screens=None, projected=None):
        screens=screen_records() if screens is None else screens
        if not screens:return QRect(0,0,560,330)
        rect=projected if projected is not None else self.projected_layout(screens)
        cfg=self.service.cfg
        target=QRect(*rect) if rect else QRect(*screens[0]['area'])
        screen=QApplication.screenAt(target.center()) or QApplication.primaryScreen();area=screen.availableGeometry()
        width=min(area.width(),cfg['resource_expanded_width']);height=min(area.height(),cfg['resource_expanded_height'])
        if (width,height)==(560,300) and not any(cfg['resource_'+k] for k in METRICS if k!='bluetooth') and not (cfg['resource_ai'] or cfg['resource_music'] or cfg['resource_ai_tray'] or cfg['resource_weather']):width=min(width,280);height=min(height,150)
        x=max(area.left(),min(round(target.x()+(target.width()-width)/2),area.right()-width+1))
        y=max(area.top(),min(target.top() if rect else area.top()+18,area.bottom()-height+1))
        return QRect(x,y,width,height)

    def projected_layout(self, screens):
        record = valid_record(self.service.cfg['resource_layout'])
        return project(record, screens, minimum=(1,1)) if record else None

    def reposition(self):
        if self.press is not None or self.liquid.landing:return
        cfg=self.service.cfg;compact=self.service.compact
        screens = screen_records()
        projected = self.projected_layout(screens)
        rect = QRect(*projected) if compact and projected else self.desktop_rect(screens, projected)
        if compact:
            kind=cfg['resource_fold']
            if kind=='ball':rect=QRect(*fold_geometry(list(rect.getRect()),{'style':'ball','ratio':80},38))
            else:
                center=rect.x()+rect.width()/2;screen=QApplication.screenAt(rect.center()) or QApplication.primaryScreen();area=screen.availableGeometry()
                from resource_compact import natural_width
                rect.setWidth(natural_width(self,min(cfg['resource_compact_width'],area.width())));rect.setHeight(cfg['resource_compact_height'])
                rect.moveLeft(max(area.left(),min(round(center-rect.width()/2),area.right()-rect.width()+1)))
        from resource_liquid import attached
        area=(QApplication.screenAt(rect.center()) or QApplication.primaryScreen()).availableGeometry()
        edge = cfg['resource_edge'] if cfg['card_snap'] and cfg['resource_edge_snap'] else 'free'
        rect=attached(rect,area,edge)
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
        self._compact_cache=None
        cfg=self.service.cfg;self.values=display_values(self.service)
        tips=[label+'  '+value+(' · '+tip if tip else '') for _,label,value,tip in self.values]
        if self.service.deck:
            from resource_quota import quota_text
            for row in self.service.deck.providers:
                quotas = [q['label'].replace(' · 已用', '')+' '+quota_text(q) for q in row.get('quotas', [])]
                tips.append(row['name']+' · '+('; '.join(quotas) or row.get('status','未连接')))
            track=self.service.deck.media.get('track') or {}
            if track:tips.append(track.get('title','')+' · '+track.get('artist',''))
        if cfg['resource_traffic']:
            from resource_traffic import amount
            data=self.service.latest.get('traffic') or {}
            for key,name in [('day','今日'),('month','本月'),('year','本年')]:
                if key in data:tips.append(name+'流量：↓ '+amount(data[key][0])+'  ↑ '+amount(data[key][1])+'  合计 '+amount(sum(data[key])))
        if self.service.compact:tips.append('滚轮切换读数，点击展开')
        self.setToolTip('');self.setAccessibleName('\n'.join(tips) or '资源胶囊 · 点击展开')
        if not self.service.compact:
            if not self.page_enabled(self.page_key):self.page_key='resources'
            self.scroll.setVisible(self.page_key=='resources')
            if self.page_key!='resources':self.view(self.page_key).show();self.view(self.page_key).refresh()
            for key in ('ai','music','traffic','weather'):
                view=getattr(self,'_'+key+'_view')
                if view and key!=self.page_key:view.hide()
        if not self.service.compact and self.page_key=='resources':
            if self.dashboard is None:
                self.build_dashboard()
            basics=[row for row in self.values if row[0] in ('cpu','gpu','memory','network')]
            self.graph.refresh(basics);self.sensor_columns.refresh([row for row in self.values if row not in basics])
            self.no_readings.setVisible(not self.values and not (cfg['resource_rank'] or cfg['resource_bluetooth']))
            self.rank_section.setVisible(cfg['resource_rank'])
            self.battery_section.setVisible(cfg['resource_bluetooth'])
            self.layout_dashboard()
            if cfg['resource_rank']:self.show_ranking()
            self.bt_head.setVisible(cfg['resource_bluetooth']);self.rings.setVisible(cfg['resource_bluetooth'])
            bt=self.service.bluetooth;self.bt_page.setVisible(bool(bt and bt.pages()>1))
            if bt:self.bt_page.setText(f'{bt.page+1}/{bt.pages()} ›')
            if cfg['resource_bluetooth']:self.rings.refresh(bt)
            self.body.activate()
            wanted=self.body.minimumSize().height()
            if self.page.minimumHeight()!=wanted:self.page.setMinimumHeight(wanted)
        for key,btn in self.page_buttons.items():
            enabled=self.page_enabled(key)
            btn.setVisible(not self.service.compact and enabled);btn.setChecked(key==self.page_key)
        self.layout_page_buttons()
        if self.service.compact:self.reposition()
        self.update()

    def resizeEvent(self,event):
        h=min(34,self.height());self.detail.setGeometry(0,h,self.width(),max(1,self.height()-h))
        if self.dashboard is not None:
            self.layout_dashboard()
        self.fold_button.setGeometry(self.width()-35,5,26,26);self.settings_button.setGeometry(self.width()-64,5,26,26)
        self.layout_page_buttons()
        if hasattr(self,'resize_edges'):self.resize_edges.sync()
        super().resizeEvent(event)
    def layout_page_buttons(self):
        x=0
        for key,btn in self.page_buttons.items():
            if not self.page_enabled(key):continue
            btn.setGeometry(x,0,44,24);x+=46
        cfg=self.service.cfg;self.header_face_width=round(30*cfg['resource_face_scale']/100) if cfg['resource_face'] else 0
        left=13+self.header_face_width if self.header_face_width else 35
        total=max(1,x-2);available=max(1,self.width()-left-69);overflow=total>available
        width=min(total,max(1,available-(36 if overflow else 0)))
        self.nav_content.setFixedSize(total,24);self.nav.setGeometry(left,5,width,24)
        visible=not self.service.compact;self.nav.setVisible(visible)
        for index,button in enumerate(self.nav_arrows):
            button.setGeometry(left+width+18*index,5,18,24);button.setVisible(visible and overflow)
        self.nav_end=left+width+(36 if overflow else 0)
    def paintEvent(self,event):
        if not self.colors:return
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);p.setRenderHint(QPainter.TextAntialiasing)
        cfg=self.service.cfg;c=self.colors;compact=self.service.compact;rect=QRectF(self.rect()).adjusted(1,1,-1,-1)
        radius=min(17,rect.height()/2) if not compact else min(12,rect.height()/2) if cfg['resource_fold']=='bar' else rect.height()/2
        self.glass.paint(p,self,self,radius,self.press is not None,self.background,4 if cfg['resource_halo'] else 0,
                         self.liquid.radii(radius),self.liquid.live)
        from resource_compact import paint_halo,paint_compact
        paint_halo(self,p)
        ink=QColor(c['ink']);accent=QColor(metric_colors(self.service)['cpu']);font=QFont(self.font());font.setPixelSize(13)
        if compact and (self.width()<70 or (cfg['resource_fold']=='ball')):
            if cfg['resource_face']:
                self.liquid.paint_face(p,rect.center(),max(20,self.width()-12));return
            q=rect.center();p.setPen(QPen(accent,2,Qt.SolidLine,Qt.RoundCap))
            for n,h in enumerate((7,14,10)):p.drawLine(QPointF(q.x()-5+5*n,q.y()+6),QPointF(q.x()-5+5*n,q.y()+6-h))
            return
        if not compact:
            if cfg['resource_face']:
                self.liquid.paint_face(p,QPointF(7+self.header_face_width/2,17),self.header_face_width)
            else:
                p.setPen(QPen(accent,2,Qt.SolidLine,Qt.RoundCap))
                for n,h in enumerate((6,13,9)):p.drawLine(16+n*4,24,16+n*4,24-h)
            font.setWeight(QFont.DemiBold);font.setPixelSize(15);p.setFont(font);p.setPen(ink)
            bridge=self.service.deck
            header_left=self.nav_end+4;header_width=max(0,self.width()-68-header_left)
            if bridge and bridge.alert_until>time.monotonic() and cfg['resource_quota_alert'] and header_width>=80:
                from resource_compact import text
                text(p,QRectF(header_left,5,header_width,24),bridge.alert,c['ink'],9)
            elif self.width()>=620 and header_width>=52 and self.service.history:
                stamp=self.service.history[-1]['time']
                sampled_at=time.time()-max(0,time.monotonic()-stamp)
                font.setPixelSize(11);font.setWeight(QFont.Normal);p.setFont(font);p.setPen(QColor(c['muted']))
                p.drawText(QRect(header_left,0,header_width,34),Qt.AlignRight|Qt.AlignVCenter,time.strftime('%H:%M',time.localtime(sampled_at)))
            return
        paint_compact(self,p)
        return

    def wheelEvent(self,event):
        if self.service.compact and event.angleDelta().y():
            self.offset+=1 if event.angleDelta().y()<0 else -1;self.update();event.accept()
        else:event.ignore()
    def enterEvent(self,event):
        self.outside_since = None
        if self.service.cfg['resource_expand_mode']=='hover' and self.service.compact:self.enter_timer.start()
        super().enterEvent(event)
    def expand_hover(self):
        if self.service.cfg['resource_expand_mode']=='hover' and self.press is None and not self.liquid.landing and self.isVisible() and self.geometry().contains(QCursor.pos()):self.service.fold(False,automatic=True)
    def leaveEvent(self,event):
        self.enter_timer.stop()
        super().leaveEvent(event)
    def fold_idle(self):
        # Native leave events can be lost when a popup or mouse grab takes over.
        if (self.press is not None or self.liquid.landing or self.geometry().contains(QCursor.pos())
                or QApplication.activePopupWidget() or QApplication.activeModalWidget()):
            self.outside_since = None
            return
        now = time.monotonic()
        if self.outside_since is None:
            self.outside_since = now
        elif now - self.outside_since >= self.service.cfg['resource_delay']:
            self.service.fold(True, automatic=True)
    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton and (event.y()<38 or self.service.compact):
            self.enter_timer.stop();self.outside_since=None;self.press=event.globalPos();self.origin=self.pos()
            self.moved=False;event.accept()
            self.liquid.begin()
        else:super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if self.press is None:return
        delta=event.globalPos()-self.press
        if delta.manhattanLength()>=QApplication.startDragDistance():self.moved=True
        if self.moved:self.move(self.origin+delta);self.liquid.moved()
    def mouseReleaseEvent(self,event):
        if event.button()!=Qt.LeftButton or self.press is None:return
        self.press=None
        self.liquid.released()
        if not self.moved:
            if self.service.compact:self.service.fold(False)
            return
        bar=self.taskbar_at(event.globalPos())
        if bar:
            self.reposition();self.service.offer_taskbar(bar,event.globalPos());return
        if self.liquid.drop(event.globalPos()):return
        rect=QRect(self.geometry())
        screen=QApplication.screenAt(event.globalPos()) or QApplication.primaryScreen();area=screen.availableGeometry()
        rect.moveLeft(max(area.left(),min(rect.x(),area.right()-rect.width()+1)))
        rect.moveTop(max(area.top(),min(rect.y(),area.bottom()-rect.height()+1)))
        if not self.service.set_options(resource_edge='free',resource_layout=capture(list(rect.getRect()),screen_records())):self.reposition()
    def contextMenuEvent(self,event):
        self.enter_timer.stop();self.outside_since=None;menu=AlignedMenu(self);cfg=self.service.cfg
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
    def hideEvent(self,event):
        self.animation.stop();self.clock_tick.stop();self.rotate.stop()
        self.enter_timer.stop();self.auto_fold_timer.stop();self.outside_since=None
        if hasattr(self,'liquid'):self.liquid.hide()
        if self.service.extras:self.service.extras.pause()
        super().hideEvent(event)
    def showEvent(self,event):
        super().showEvent(event)
        self.sync_auto_fold()
        if self.colors:self.sync_animation();self.liquid.sync()
        if self.service.extras:self.service.extras.sync()
    def dispose(self):
        self.liquid.close()
        self.animation.stop();self.clock_tick.stop();self.rotate.stop()
        self.enter_timer.stop();self.auto_fold_timer.stop();self.glass.clear();self.hide();self.deleteLater()


from resource_settings import ResourceOptions
