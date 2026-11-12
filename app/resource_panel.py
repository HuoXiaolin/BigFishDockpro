"""Movable monitor panel. Compact and expanded states share one header-centre anchor."""
from html import escape
from math import ceil
import time
from PyQt5.QtCore import Qt,QEvent,QRect,QRectF,QPoint,QPointF,QSize,QTimer
from PyQt5.QtGui import QColor,QPainter,QPainterPath,QPen,QFont,QFontMetrics,QCursor,QPixmap,QPalette,QRegion
from PyQt5.QtWidgets import (QWidget,QLabel,QToolButton,QFrame,QScrollArea,
    QVBoxLayout,QHBoxLayout,QGridLayout,QFormLayout,QLayout,QApplication,QSizePolicy)
from ui_style import AlignedMenu
from component_passthrough import enabled as passthrough_enabled
from screen_layout import screen_records,valid_record,capture,project
from fold_options import geometry as fold_geometry
from resource_options import (COMPACT_STATUS,DESKTOP_COMPONENTS,FAN_METRICS,HALO_SPEEDS,METRICS,OPEN_PAGES,SENSOR_UNITS,
                              background,component_available,component_location,content_columns)
from flash_view import palette_for,icon


from resource_charts import DashboardCard,MetricDisplay,SensorColumns,rate,metric_colors,sync_card_controls
from capsule_glass import CapsuleGlass


COMPACT_PAGES={**dict.fromkeys(COMPACT_STATUS,'resources'),'weather':'weather','music':'music','ai':'ai'}
COMPACT_FRAME_MS = 16
COMPACT_SCROLL_SECONDS = .24


def display_values(service,compact=None):
    cfg=service.cfg;data=service.latest;rows=[]
    compact=service.compact if compact is None else compact
    for key in ('cpu','memory','network','gpu','fps',*SENSOR_UNITS):
        if not cfg['resource_'+key]:continue
        if compact and key not in cfg['resource_compact_metrics']:continue
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
                if key in FAN_METRICS or cfg['resource_hide_unavailable']:continue
                tip='当前传感器未提供读数'
        if key=='gpu':tip='所有显卡中最忙引擎的利用率' if value is not None else '等待显卡驱动计数器'
        rows.append((key,label,display,tip))
    return rows


class BatteryRows(QWidget):
    name_x=46
    gap=7

    def __init__(self,window):
        super().__init__()
        self.owner_window=window
        self.legend=[]
        self.status=''
        self.setFixedHeight(17)

    def refresh(self,rows,status):
        if rows==self.legend and status==self.status:return
        self.legend=rows;self.status=status
        height=17*max(1,len(self.legend))
        if self.height()!=height:self.setFixedHeight(height)
        summary='\n'.join(f"{self.source_name(row)} · {row['name']} · {row['display_value']}" for row in rows) or status
        self.setToolTip('<qt>'+escape(summary).replace('\n','<br>')+'</qt>')
        self.setAccessibleName(summary);self.update()

    @staticmethod
    def source_name(row):
        return '2.4G' if row['source']=='2.4g' else '蓝牙'

    def paintEvent(self,event):
        from bluetooth_gauge import draw_peripheral_rings,ring_ink
        from resource_status import BATTERY_WARNING_LEVEL
        p=QPainter(self);p.setRenderHints(QPainter.Antialiasing|QPainter.TextAntialiasing)
        c=self.owner_window.colors
        font=QFont(self.font());font.setPixelSize(10);p.setFont(font)
        if not self.legend:
            p.setPen(QColor(c['muted']));width=max(1,self.width())
            p.drawText(QRect(0,0,width,17),Qt.AlignVCenter,p.fontMetrics().elidedText(self.status,Qt.ElideRight,width))
            return
        metrics=p.fontMetrics();value_font=QFont(font);value_font.setWeight(QFont.DemiBold)
        name_x=self.name_x;gap=self.gap
        numbers=QFontMetrics(value_font)
        readings=[row['display_value'] for row in self.legend]
        available=max(2,self.width()-name_x-gap-2)
        value_width=min(max(numbers.horizontalAdvance(value) for value in readings)+2,max(1,available-20))
        name_width=max(1,min(112,available-value_width,
                             max(metrics.horizontalAdvance(row['name']) for row in self.legend)))
        value_x=name_x+name_width+gap
        for i,(row,value) in enumerate(zip(self.legend,readings)):
            y=17*i
            p.setPen(QColor(c['muted']));p.setFont(font)
            p.drawText(QRect(0,y,27,17),Qt.AlignVCenter,self.source_name(row))
            draw_peripheral_rings(p,QRectF(28,y+1,14,14),[row],not c['light'])
            p.setPen(QColor(c['ink']));p.setFont(font)
            p.drawText(QRect(name_x,y,name_width+1,17),Qt.AlignVCenter,metrics.elidedText(row['name'],Qt.ElideRight,name_width+1))
            low=row['level'] is not None and row['level']<BATTERY_WARNING_LEVEL
            tinted=low or row.get('state')=='charging' or row.get('stale')
            p.setPen(QColor(ring_ink(row,c['light']) if tinted else c['ink']))
            p.setFont(value_font);p.drawText(QRect(value_x,y,value_width,17),Qt.AlignRight|Qt.AlignVCenter,numbers.elidedText(value,Qt.ElideRight,value_width))


class CapsuleTab(QToolButton):
    def __init__(self,owner,key,title,parent):
        super().__init__(parent)
        self.owner=owner
        self.key=key
        self.drag_start=None
        self.dragging=False
        self.setText(title)
        self.setAccessibleName(title)
        self.setToolTip(title+' · 拖动排序，拖出胶囊后独立显示')
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(True)
        self.setFocusPolicy(Qt.StrongFocus)

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:
            self.drag_start=event.globalPos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self.drag_start is not None and (self.dragging or (event.globalPos()-self.drag_start).manhattanLength()>=QApplication.startDragDistance()):
            if not self.dragging:
                self.dragging=True
                self.setDown(False)
                self.setCursor(Qt.ClosedHandCursor)
            self.owner.preview_tab_drop(self.key,event.globalPos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.LeftButton and self.drag_start is not None:
            moved=self.dragging or (event.globalPos()-self.drag_start).manhattanLength()>=QApplication.startDragDistance()
            self.cancel_drag()
            if moved:
                self.setDown(False)
                self.owner.finish_tab_drop(self.key,event.globalPos())
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def cancel_drag(self):
        self.drag_start=None
        if self.dragging:
            self.dragging=False
            self.setDown(False)
            self.setCursor(Qt.PointingHandCursor)
            self.owner.clear_tab_drop()

    def event(self,event):
        if event.type() in (QEvent.Hide,QEvent.UngrabMouse) and getattr(self,'drag_start',None) is not None:
            self.cancel_drag()
        return super().event(event)

    def keyPressEvent(self,event):
        if event.key()==Qt.Key_Escape and self.dragging:
            self.cancel_drag()
            event.accept()
        else:super().keyPressEvent(event)

    def paintEvent(self,event):
        colors=self.owner.colors
        if not colors:return
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        selected=self.isChecked()
        if selected or self.underMouse() or self.hasFocus():
            fill=QColor(colors['hover']);fill.setAlpha(86 if selected else 48)
            edge=self.palette().color(QPalette.Link) if self.hasFocus() else QColor(colors['ink'])
            edge.setAlpha(185 if self.hasFocus() else 65)
            painter.setPen(QPen(edge,1) if selected or self.hasFocus() else Qt.NoPen)
            painter.setBrush(fill)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(1.5,1.5,-1.5,-1.5),6,6)
        font=QFont(self.font());font.setPixelSize(11);font.setWeight(QFont.DemiBold if selected else QFont.Medium)
        painter.setFont(font)
        painter.setPen(QColor(colors['ink'] if selected else colors['muted']))
        painter.drawText(self.rect(),Qt.AlignCenter,self.text())


class ResourceContentHost(QWidget):
    """Shared page surface and hardware dashboard for the capsule and desktop cards."""
    battery_page_size=3

    def __init__(self,service,hardware=True):
        super().__init__(None,Qt.Tool|Qt.FramelessWindowHint|Qt.NoDropShadowWindowHint)
        self.service=service
        self.rank_by='cpu'
        self.rank_labels=[]
        self.rank_icons={}
        self.dashboard=None
        self.battery_page=0
        self.colors={}
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.detail=QWidget(self)
        layout=QVBoxLayout(self.detail)
        layout.setContentsMargins(12,0,12,10)
        layout.setSpacing(2)
        if hardware:
            from resource_pages import CapsuleScrollArea
            self.scroll=CapsuleScrollArea()
            layout.addWidget(self.scroll)
        self.glass=CapsuleGlass()
        self.init_style()

    def sync_palette(self):
        previous=getattr(self,'background',None)
        self.background=background(self.service.cfg)
        if self.dashboard is not None and previous!=self.background:self.dashboard.update()
        colors=palette_for(self.service,self.background)
        if colors['light']:colors['muted']='#415266'
        colors['card_alpha']=round(255*(100-self.service.cfg['resource_card_transparency'])/100)
        if colors==self.colors:
            return False
        self.colors=colors
        palette=self.palette()
        for role,key in ((QPalette.WindowText,'ink'),(QPalette.Text,'ink'),(QPalette.ButtonText,'ink'),
                         (QPalette.Base,'field'),(QPalette.Button,'hover'),(QPalette.Mid,'muted'),
                         (QPalette.Highlight,'hover'),(QPalette.HighlightedText,'ink')):
            palette.setColor(role,QColor(colors[key]))
        self.setPalette(palette)
        if self.dashboard is not None:sync_card_controls(self.dashboard,colors)
        return True

    def init_style(self):
        from resource_pages import SCROLL_STYLE
        self.setStyleSheet("""
            QWidget{background:transparent;color:palette(window-text)}
            QLabel{font-size:10px}
            QLabel#RankTitle{font-weight:600}
            QLabel#RankMemory,QLabel#Subtle{color:palette(mid);font-size:10px}
            QToolButton{border:1px solid transparent;border-radius:6px;padding:2px 5px;color:palette(mid);background:transparent;font-size:10px}
            QToolButton:hover{background:rgba(123,145,161,46);color:palette(window-text)}
            QToolButton:checked{background:rgba(123,145,161,69);border-color:rgba(123,145,161,105);color:palette(window-text)}
            QToolButton#RankSort{font-size:10px;padding:2px 5px}
            QScrollArea{border:0}
            QTableWidget{background:transparent;border:0;selection-background-color:palette(button);font-size:12px}
            QHeaderView::section{background:palette(button);color:palette(mid);border:0;padding:5px;font-size:11px}
            QTableCornerButton::section{background:palette(button);border:0}
            QDateEdit{background:palette(button);color:palette(window-text);border:0;border-radius:5px;padding:4px}
            QSlider::groove:horizontal{background:palette(button);height:4px;border:0;border-radius:2px}
            QSlider::sub-page:horizontal{background:palette(mid);border-radius:2px}
            QSlider::handle:horizontal{background:palette(window-text);width:12px;margin:-4px 0;border-radius:6px}
        """ + SCROLL_STYLE)

    def build_dashboard(self):
        page=QWidget();self.scroll.setWidget(page);body=QVBoxLayout(page);body.setContentsMargins(2,2,4,1);body.setSpacing(7);body.setSizeConstraint(QLayout.SetMinAndMaxSize);self.body=body;self.page=page
        self.dashboard=QWidget(page)
        self.columns=QGridLayout(self.dashboard)
        self.columns.setContentsMargins(0,0,0,0)
        self.columns.setHorizontalSpacing(7);self.columns.setVerticalSpacing(7)
        self.columns.setColumnStretch(0,3);self.columns.setColumnStretch(1,2)
        self.dashboard_layout_key = None
        self.graph=MetricDisplay(self)
        self.graph.setParent(self.dashboard)
        self.rank_section=DashboardCard(self,'lavender',self.dashboard)
        rank_body=QVBoxLayout(self.rank_section)
        rank_body.setContentsMargins(9,6,9,7);rank_body.setSpacing(3)
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
        self.battery_actions=QWidget();row=QHBoxLayout(self.battery_actions);row.setContentsMargins(0,0,0,0)
        row.setSpacing(4)
        self.battery_next=QToolButton();self.battery_next.setAccessibleName('下一组外设电量')
        self.battery_next.clicked.connect(self.next_devices);row.addWidget(self.battery_next)
        self.battery_refresh=QToolButton();self.battery_refresh.setAccessibleName('刷新外设电量')
        self.battery_refresh.setToolTip('刷新外设电量');self.battery_refresh.clicked.connect(self.service.refresh_batteries);row.addWidget(self.battery_refresh)
        self.battery_section=DashboardCard(self,'mint',self.dashboard);battery_layout=QVBoxLayout(self.battery_section)
        battery_layout.setContentsMargins(9,6,9,7);battery_layout.setSpacing(1)
        top=QHBoxLayout();top.setSpacing(4)
        self.battery_title=QLabel('电脑状态');self.battery_title.setObjectName('RankTitle');top.addWidget(self.battery_title,1)
        top.addWidget(self.battery_actions);battery_layout.addLayout(top)
        from resource_system_view import SystemReadout
        self.system_readout=SystemReadout(self);battery_layout.addWidget(self.system_readout)
        self.rings=BatteryRows(self);battery_layout.addWidget(self.rings)
        battery_layout.addStretch(1)
        body.addStretch()
        sync_card_controls(self.dashboard,self.colors)

    def layout_dashboard(self):
        groups = ((self.graph, self.rank_section), (self.sensor_columns, self.battery_section))
        visible = tuple(tuple(panel for panel in group if not panel.isHidden()) for group in groups)
        wide = content_columns(self.width()) == 2
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
                self.columns.addWidget(panel, row, column, 1, span)
        self.dashboard.setVisible(any(visible))

    def release_dashboard(self):
        if self.dashboard is None:
            return
        page = self.scroll.takeWidget()
        self.dashboard = None
        self.rank_labels = []
        self.rank_icons.clear()
        for name in ('columns','graph','rank_section','rank_head','rank_buttons','rank_widget',
                     'dashboard_layout_key','sensor_columns','no_readings','battery_actions','battery_next',
                     'battery_refresh','battery_section','battery_title','system_readout','rings','body','page'):
            self.__dict__.pop(name, None)
        if page is not None:
            page.deleteLater()

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
        self.refresh_battery_rows(1)

    def refresh_battery_rows(self,step=0):
        if self.dashboard is None:return
        cfg=self.service.cfg
        enabled=bool(cfg['resource_bluetooth'] or cfg.get('resource_peripheral_profiles'))
        self.battery_actions.setVisible(enabled)
        self.rings.setVisible(enabled)
        if not enabled:
            self.battery_page=0
            self.rings.refresh([],'')
            return
        rows=self.service.battery_rows()
        size=self.battery_page_size
        pages=max(1,(len(rows)+size-1)//size)
        self.battery_page=(min(self.battery_page,pages-1)+step)%pages
        self.battery_next.setVisible(pages>1)
        self.battery_next.setText(f'{self.battery_page+1}/{pages} ›')
        ink=self.colors['muted']
        if self.battery_refresh.property('iconInk')!=ink:
            self.battery_refresh.setProperty('iconInk',ink)
            self.battery_refresh.setIcon(icon('refresh',ink,13));self.battery_refresh.setIconSize(QSize(13,13))
        start=self.battery_page*size
        self.rings.refresh(rows[start:start+size],'' if rows else self.service.battery_status())

    def refresh_dashboard(self):
        cfg=self.service.cfg
        if self.dashboard is None:
            self.build_dashboard()
        basics=[row for row in self.values if row[0] in ('cpu','gpu','memory','network')]
        self.graph.refresh(basics);self.sensor_columns.refresh([row for row in self.values if row not in basics])
        peripherals=bool(cfg.get('resource_peripheral_profiles'))
        self.no_readings.setVisible(not self.values and not (cfg['resource_rank'] or cfg['resource_bluetooth'] or cfg['resource_system_status'] or peripherals))
        self.rank_section.setVisible(cfg['resource_rank'])
        self.battery_section.setVisible(cfg['resource_bluetooth'] or cfg['resource_system_status'] or peripherals)
        self.battery_title.setText('电脑状态' if cfg['resource_system_status'] else '外设电量')
        self.system_readout.setVisible(cfg['resource_system_status'])
        if cfg['resource_system_status']:self.system_readout.refresh()
        self.layout_dashboard()
        if cfg['resource_rank']:self.show_ranking()
        self.refresh_battery_rows()
        self.body.activate()
        wanted=self.body.minimumSize().height()
        if self.page.minimumHeight()!=wanted:self.page.setMinimumHeight(wanted)


class ResourceWindow(ResourceContentHost):
    def __init__(self,service):
        super().__init__(service)
        self.setProperty('clickThroughKey','resource')
        self.press=None;self.offset=0;self.last_layer=None
        self.taskbar_placement=None
        self.taskbar_size=None
        self.page_key='resources';self._displayed_compact=None;self.halo_phase=0.;self.compact_pages=1
        self.halo_updated_at = None
        self.compact_scroll = None
        self.compact_scroll_pending = 0
        self.setWindowTitle('资源胶囊 · 大肥鱼Dock');self.setAccessibleName('系统资源监控')
        self._ai_view=self._music_view=None
        self._traffic_view=self._weather_view=None
        self._news_view=self._pomodoro_view=self._agenda_view=None
        self._reminder_key=();self.reminder_bounds=();self.reminder_kinds=()
        self.status_bounds={};self.marquee_title='';self.marquee_since=0.;self.marquee_span=0
        for key in DESKTOP_COMPONENTS:setattr(self,'_'+key+'_view',None)
        self.empty_page=QLabel('把桌面组件拖回胶囊，或在「组件布局」中选择栏目。')
        self.empty_page.setObjectName('Subtle');self.empty_page.setWordWrap(True)
        self.detail.layout().addWidget(self.empty_page);self.empty_page.hide()
        self._saved_view_state = {}
        self.nav=QScrollArea(self);self.nav.setFrameShape(QFrame.NoFrame)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);self.nav.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav_content=QWidget();self.nav.setWidget(self.nav_content)
        self.tab_drag=None
        self.tab_drop_mark=None
        self.tab_scroll_direction=0
        self.tab_scroll=QTimer(self)
        self.tab_scroll.setInterval(90)
        self.tab_scroll.timeout.connect(self.scroll_tab_drag)
        self.nav_arrows=[]
        for title,direction in [('‹',-1),('›',1)]:
            button=QToolButton(self);button.setText(title);button.setAccessibleName('向左切换栏目' if direction<0 else '向右切换栏目')
            button.clicked.connect(lambda checked=False,d=direction:self.nav.horizontalScrollBar().setValue(self.nav.horizontalScrollBar().value()+d*100));self.nav_arrows.append(button)
        self.page_buttons={}
        for key,title in tuple(OPEN_PAGES.items())[1:]:
            btn=CapsuleTab(self,key,title,self.nav_content)
            btn.clicked.connect(lambda checked=False,key=key:self.select_page(key));self.page_buttons[key]=btn
        self.settings_button=QToolButton(self);self.settings_button.setAccessibleName('资源胶囊设置');self.settings_button.setToolTip('资源胶囊设置');self.settings_button.clicked.connect(service.settings)
        self.fold_button=QToolButton(self);self.fold_button.setAccessibleName('收起胶囊');self.fold_button.setToolTip('收起胶囊');self.fold_button.clicked.connect(lambda:service.fold(True))
        self.outside_since = None
        self.auto_fold_timer = QTimer(self)
        self.auto_fold_timer.setInterval(250)
        self.auto_fold_timer.timeout.connect(self.fold_idle)
        self.enter_timer=QTimer(self);self.enter_timer.setSingleShot(True);self.enter_timer.setInterval(230);self.enter_timer.timeout.connect(self.expand_hover)
        self.animation=QTimer(self)
        self.animation.setTimerType(Qt.PreciseTimer)
        self.animation.setInterval(COMPACT_FRAME_MS)
        self.animation.timeout.connect(self.animate)
        self.clock_tick=QTimer(self);self.clock_tick.setInterval(1000);self.clock_tick.timeout.connect(self.update)
        self.rotate=QTimer(self);self.rotate.setInterval(6000);self.rotate.timeout.connect(self.next_page)
        self._wallpaper_key = None
        self.wallpaper_timer = QTimer(self)
        self.wallpaper_timer.setInterval(5000)
        self.wallpaper_timer.timeout.connect(self.refresh_wallpaper)
        from resource_resize import ResizeEdges
        self.resize_edges=ResizeEdges(self)
        from resource_liquid import CapsuleMotion
        self.liquid=CapsuleMotion(self)





    def select_page(self,key):
        before=self.service.needs()
        previous=self.page_key
        self.page_key='ai' if key=='stats' else key
        self.refresh();self.reposition()
        if self.page_key and self.page_key!=previous and not self.service.compact:
            if self.page_key=='resources':scroll=self.scroll
            elif self.page_key=='ai':scroll=self.ai_view.statistics.scroll
            else:scroll=self.view(self.page_key)
            scroll.verticalScrollBar().setValue(0)
        if self.page_key:self.nav.ensureWidgetVisible(self.page_buttons[self.page_key],0,0)
        if before!=self.service.needs():self.service.sync()
        else:
            if self.service.deck:self.service.deck.configure()
            if self.service.pomodoro:self.service.pomodoro.sync()
    def page_enabled(self,key):
        cfg=self.service.cfg
        return key in self.page_buttons and component_location(cfg,key)=='capsule' and component_available(cfg,key)

    def first_page(self):
        return next((key for key in self.service.cfg['resource_component_order'] if self.page_enabled(key)),None)

    def tab_drop_slot(self,key,point):
        local=self.mapFromGlobal(point)
        nav=self.nav.geometry()
        if self.service.compact or not (nav.top()<=local.y()<=nav.bottom() and nav.left()<=local.x()<self.nav_end):
            return None
        x=min(local.x(),nav.right())-nav.left()+self.nav.horizontalScrollBar().value()
        buttons=[(name,self.page_buttons[name]) for name in self.service.cfg['resource_component_order']
                 if name!=key and self.page_enabled(name)]
        if not buttons:
            return None
        before, marker=None,buttons[-1][1].geometry().right()+1
        for name,button in buttons:
            if x<=button.geometry().center().x():
                before,marker=name,button.x()
                break
        marker=max(nav.left()+1,min(nav.right()-1,nav.left()+marker-self.nav.horizontalScrollBar().value()))
        return before, QRect(marker,nav.top()+2,2,nav.height()-4)

    def preview_tab_drop(self,key,point,*,incoming=False):
        if incoming and not self.geometry().contains(point):
            self.clear_tab_drop()
            return
        self.tab_drag=(key,point,incoming)
        self.update_tab_drop()

    def update_tab_drop(self):
        key,point,incoming=self.tab_drag
        slot=self.tab_drop_slot(key,point)
        nav=self.nav.geometry()
        x=self.mapFromGlobal(point).x()
        bar=self.nav.horizontalScrollBar()
        direction=0
        if slot is not None:
            if x-nav.left()<14 and bar.value()>bar.minimum():direction=-1
            if nav.right()-x<14 and bar.value()<bar.maximum():direction=1
        self.tab_scroll_direction=direction
        if direction and not self.tab_scroll.isActive():self.tab_scroll.start()
        elif not direction:self.tab_scroll.stop()
        if slot is None and not incoming:
            if self.tab_drop_mark:self.tab_drop_mark.hide()
            return
        if self.tab_drop_mark is None:
            self.tab_drop_mark=QFrame(self)
            self.tab_drop_mark.setAttribute(Qt.WA_TransparentForMouseEvents)
        marker=self.tab_drop_mark
        ink=self.palette().color(QPalette.Link).name()
        style=f'background:{ink};border:0;' if slot else f'background:transparent;border:2px solid {ink};border-radius:9px;'
        if marker.styleSheet()!=style:marker.setStyleSheet(style)
        marker.setGeometry(slot[1] if slot else self.rect().adjusted(2,2,-2,-2))
        marker.show()
        marker.raise_()

    def scroll_tab_drag(self):
        if self.tab_drag:
            bar=self.nav.horizontalScrollBar()
            bar.setValue(bar.value()+32*self.tab_scroll_direction)
            self.update_tab_drop()

    def clear_tab_drop(self):
        self.tab_drag=None
        self.tab_scroll.stop()
        if self.tab_drop_mark:self.tab_drop_mark.hide()

    def finish_tab_drop(self,key,point):
        self.clear_tab_drop()
        slot=self.tab_drop_slot(key,point)
        if slot is not None:
            self.service.set_options(resource_component_order=self.service.component_order_at(key,slot[0]))
        elif not self.geometry().contains(point) and QApplication.screenAt(point) is not None:
            self.service.detach_component_at(key,point)

    def view(self,key):
        view=getattr(self,'_'+key+'_view')
        if view is None:
            from resource_pages import AiView,MusicView,InfoPage
            if key in DESKTOP_COMPONENTS:
                from capsule_components import CapsuleComponentView
                view=CapsuleComponentView(self,key)
            else:view=AiView(self) if key=='ai' else MusicView(self) if key=='music' else InfoPage(self,key)
            setattr(self,'_'+key+'_view',view);view.hide();self.detail.layout().addWidget(view)
            state = self._saved_view_state.pop(key, None)
            if state and key == 'ai':
                period, metric, provider, dates = state
                view.statistics.period = period
                view.statistics.metric = metric
                view.statistics.refresh()
                view.statistics.provider.setCurrentIndex(max(0, view.statistics.provider.findData(provider)))
                view.detail_dates = dates
            elif state and key == 'weather':
                city, remarks = state
                view.content.refresh()
                view.content.city.setCurrentIndex(max(0, view.content.city.findText(city)))
                view.content.remarks_button.setChecked(remarks)
            elif state and key == 'traffic':
                view.content.remarks.setChecked(True)
            elif state and key == 'agenda':
                view.content.calendar.setSelectedDate(state)
            elif state and key == 'custom':
                view.selected = state
        return view

    def release_inactive_views(self):
        if not self.scroll.isVisible():
            self.release_dashboard()
        for key in tuple(self.page_buttons)[1:]:
            name = '_' + key + '_view'
            view = getattr(self, name)
            if view is None or view.isVisible():
                continue
            if key == 'ai':
                if view._detail_dialog is not None and view._detail_dialog.isVisible():
                    continue
                statistics = view.statistics
                dates = (view.start.date(), view.end.date()) if view._detail_dialog is not None else view.detail_dates
                self._saved_view_state[key] = (statistics.period, statistics.metric, statistics.provider.currentData(), dates)
            elif key == 'weather':
                self._saved_view_state[key] = (view.content.city.currentText(), view.content.remarks_button.isChecked())
            elif key == 'traffic':
                self._saved_view_state[key] = view.content.remarks.isChecked()
            elif key == 'agenda':
                self._saved_view_state[key] = view.content.calendar.selectedDate()
            elif key == 'custom':
                self._saved_view_state[key] = view.selected
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
    def refresh_reminders(self):
        if not self.isVisible():return
        if self.service.compact:
            from resource_compact import compact_badges
            badges,_=compact_badges(self.service)
            key=tuple((kind,value if kind in ('agenda','water') else '') for kind,value in badges)
            self._compact_cache=None
            if key!=self._reminder_key:
                self._reminder_key=key;self.reposition()
            self.sync_animation();self.update()
        elif self.page_key in ('pomodoro','agenda'):
            view=getattr(self,'_'+self.page_key+'_view')
            if view:view.refresh()

    def animate(self):
        cfg=self.service.cfg;now=time.monotonic()
        finishing_scroll=bool(self.compact_scroll and now-self.compact_scroll[1]>=COMPACT_SCROLL_SECONDS)
        if cfg['resource_halo']:
            _, period = HALO_SPEEDS[cfg['resource_halo_speed']]
            if self.halo_updated_at is not None:
                self.halo_phase = (self.halo_phase + (now - self.halo_updated_at) / period) % 1
            self.halo_updated_at = now
        if self.compact_scroll and now - self.compact_scroll[1] >= COMPACT_SCROLL_SECONDS:
            pending = self.compact_scroll_pending
            self.compact_scroll = None
            self.compact_scroll_pending = 0
            if pending:
                self.shift_compact_page(pending)
            self.sync_animation()
        elif self.marquee_span and not cfg['resource_halo']:
            interval = self.animation_interval(now)
            if self.animation.interval() != interval:
                self.animation.setInterval(interval)
        if finishing_scroll:
            self.update()
            return
        from resource_compact import halo_damage,marquee_frame
        damage=halo_damage(self) if cfg['resource_halo'] else QRegion()
        surface=getattr(self,'_compact_surface',None)
        if self.service.compact and surface:
            for kind,area,*_ in surface[3]:
                if kind=='scroll' or kind=='marquee' and self.marquee_span:
                    # Include the reset frame, then leave the text still during
                    # its five-second pause while the halo keeps moving.
                    shift=marquee_frame(now-self.marquee_since,self.marquee_span)[0] if kind=='marquee' else None
                    if kind=='scroll' or shift!=getattr(self,'_marquee_shift',None):
                        damage|=QRegion(area.toAlignedRect().adjusted(-1,-1,1,1))
                    if kind=='marquee':self._marquee_shift=shift
        elif self.service.compact:
            damage=QRegion(self.rect())
        if not damage.isEmpty():self.update(damage)

    def update_music_levels(self):
        if not self.isVisible():return
        if self.service.compact and getattr(self,'compact_media',False) and self.service.cfg['resource_music_text']=='wave':
            surface=getattr(self,'_compact_surface',None)
            if not surface or self.compact_scroll:
                self.update()
            else:
                for kind,area,*_ in surface[3]:
                    if kind=='wave':self.update(area.toAlignedRect())
        elif not self.service.compact:
            view=getattr(self,'_music_view',None)
            if view and view.isVisible():view.meter.update()

    def animation_interval(self, now):
        if not self.service.compact:
            return 33
        if self.compact_scroll:
            return COMPACT_FRAME_MS
        if self.marquee_span and not self.service.cfg['resource_halo']:
            from resource_compact import marquee_frame
            _, pause = marquee_frame(now - self.marquee_since, self.marquee_span)
            return max(COMPACT_FRAME_MS, ceil(pause * 1000))
        return COMPACT_FRAME_MS

    def next_page(self):
        if self.press is None and not self.underMouse():
            self.shift_compact_page(1)

    def shift_compact_page(self, step):
        cfg = self.service.cfg
        if not self.service.compact or not self.isVisible() or cfg['resource_fold']=='ball' or self.width()<70:
            return
        from resource_compact import plan
        count = len(plan(self, self.width())['pages'])
        if count <= 1:
            return
        if self.compact_scroll:
            self.compact_scroll_pending += step
            return
        previous = self.offset
        self.offset += step
        if cfg.get('motion_enabled', True) and step % count:
            self.compact_scroll = (previous, time.monotonic(), 1 if step > 0 else -1)
            if not self.animation.isActive() or self.animation.interval() != COMPACT_FRAME_MS:
                self.animation.start(COMPACT_FRAME_MS)
        self.update()

    def settle_compact_scroll(self):
        self.offset += self.compact_scroll_pending
        self.compact_scroll_pending = 0
        self.compact_scroll = None

    def sync_animation(self):
        cfg=self.service.cfg;visible=self.isVisible()
        motion=visible and cfg.get('motion_enabled',True)
        scrollable = motion and self.service.compact and cfg['resource_fold']!='ball' and self.width()>=70
        if self.compact_scroll and not scrollable:
            self.settle_compact_scroll()
        now = time.monotonic()
        title, span = '', 0
        if scrollable and self.service.agenda:
            from resource_compact import agenda_marquee
            title, span = agenda_marquee(self)
        if title != self.marquee_title:
            self.marquee_title = title
            self.marquee_since = now
        self.marquee_span = span
        if motion and cfg['resource_halo']:
            if not self.animation.isActive() or self.halo_updated_at is None:
                self.halo_updated_at = now
        else:
            self.halo_updated_at = None
        if motion and (cfg['resource_halo'] or title or self.compact_scroll):
            interval = self.animation_interval(now)
            if not self.animation.isActive() or self.animation.interval() != interval:
                self.animation.start(interval)
        else:
            self.animation.stop()
        for timer,active in [(self.clock_tick,visible and self.service.compact and cfg['resource_clock']),
                             (self.rotate,visible and self.service.compact and cfg['resource_compact_rotate'])]:
            if active and not timer.isActive():
                timer.start()
            elif not active:timer.stop()

    def sync_auto_fold(self):
        if self.isVisible() and not self.service.compact and self.service.cfg['resource_auto_hide']:
            if not self.auto_fold_timer.isActive():
                self.auto_fold_timer.start()
        else:
            self.auto_fold_timer.stop()
            self.outside_since = None

    def sync_wallpaper(self):
        if not self.isVisible() or self.service.runtime.dock.preview or self.background['material'] in ('clear','solid'):
            self.wallpaper_timer.stop()
        elif not self.wallpaper_timer.isActive():
            self.refresh_wallpaper()
            self.wallpaper_timer.start()

    def refresh_wallpaper(self):
        if self.press is not None or self.liquid.landing:
            return
        # Some wallpaper changes arrive without the native setting notification.
        from wallpaper_source import wallpaper_key
        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        if screen is None:
            return
        try:
            key = wallpaper_key(self, screen)
        except (OSError, ValueError, RuntimeError, AttributeError):
            return
        if key != self._wallpaper_key:
            self._wallpaper_key = key
            self.glass.clear()
            self.update()

    def sync_window(self):
        self.liquid.prepare()
        cfg=self.service.cfg
        previous=getattr(self,'background',None)
        palette_changed=self.sync_palette()
        if palette_changed:
            self.settings_button.setIcon(icon('settings',self.colors['ink']));self.fold_button.setIcon(icon('collapse',self.colors['ink']))
            for btn in (self.settings_button,self.fold_button):btn.setIconSize(QSize(15,15))
        compact = self.service.compact
        if not compact or cfg['resource_fold']=='ball':
            self._compact_surface=None
        opening = False
        # Temporarily folding the card while settings are open is not a new visit.
        if not self.service.editing or self.service.preview_detail:
            opening = not compact and self._displayed_compact is not False
            self._displayed_compact = compact
            preferred = cfg['resource_open_page']
            if opening and preferred != 'last':
                self.page_key = preferred if self.page_enabled(preferred) else self.first_page()
        self.detail.setVisible(not compact)
        self.settings_button.setVisible(not compact);self.fold_button.setVisible(not compact)
        if compact or not cfg['resource_rank']:
            self.rank_icons.clear();self.rank_frame=self.rank_style=None
            for mark,*_ in self.rank_labels:mark.clear()
        if cfg['resource_expand_mode']!='hover' or passthrough_enabled(cfg,'resource'):self.enter_timer.stop()
        self.sync_taskbar();self.reposition();self.refresh();self.sync_animation()
        if (palette_changed or previous!=self.background) and not compact and self.page_key in DESKTOP_COMPONENTS:
            self.service.runtime.sync_hosted_component(self.page_key)
        self.sync_auto_fold()
        self.sync_wallpaper()
        if opening and self.page_key:
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
        slot=self.taskbar_slot()
        if slot is not None and self.taskbar_placement.suppressed():
            self.hide();return
        rect=self.taskbar_rect(slot) if slot is not None else self.floating_rect(compact)
        if self.geometry()!=rect:self.setGeometry(rect)
        self.show();self.layer()
        from window_layers import click_through
        click_through(self,passthrough_enabled(cfg,'resource'))

    def floating_rect(self,compact):
        cfg=self.service.cfg
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
        edge = cfg['resource_edge'] if self.liquid.edge_snap else 'free'
        return attached(rect,area,edge)

    def sync_taskbar(self):
        cfg=self.service.cfg
        if not cfg['resource_capsule_taskbar']:
            if self.taskbar_placement and (not self.taskbar_placement.proposal or self.taskbar_size is not None):
                placement,self.taskbar_placement=self.taskbar_placement,None
                placement.close();self.taskbar_size=None
            return
        placement=self.ensure_taskbar_placement()
        placement.restore()
        size=(cfg['resource_fold'],cfg['resource_compact_width'],cfg['resource_compact_height'])
        if self.taskbar_size is not None and self.taskbar_size!=size:placement.schedule_check()
        self.taskbar_size=size

    def ensure_taskbar_placement(self):
        if self.taskbar_placement is None:
            from resource_taskbar import Placement
            self.taskbar_placement=Placement(self,capsule=True)
        return self.taskbar_placement

    def taskbar_slot(self):
        placement=self.taskbar_placement
        if placement and (placement.proposal or placement.slot_bar==placement.target):return placement.slot
        return None

    def taskbar_width(self,bar):
        cfg=self.service.cfg;rect=bar['rect']
        vertical=rect.height()>rect.width()
        if cfg['resource_fold']=='ball' or vertical:
            thickness=rect.width() if vertical else rect.height()
            return min(thickness-4,38 if cfg['resource_fold']=='ball' else cfg['resource_compact_height'])
        return cfg['resource_compact_width']

    def taskbar_rect(self,slot):
        cfg=self.service.cfg;bar=self.taskbar_placement.slot_bar['rect']
        vertical=bar.height()>bar.width()
        if self.service.compact:
            if vertical or cfg['resource_fold']=='ball':
                width=height=min(slot.width(),slot.height(),self.taskbar_width(self.taskbar_placement.slot_bar))
            else:
                from resource_compact import natural_width
                width=natural_width(self,min(slot.width(),cfg['resource_compact_width']))
                height=min(slot.height(),cfg['resource_compact_height'])
            return QRect(slot.x()+(slot.width()-width)//2,slot.y()+(slot.height()-height)//2,width,height)
        screen=QApplication.screenAt(slot.center()) or QApplication.primaryScreen()
        area=screen.availableGeometry();center=slot.center()
        width=min(area.width(),cfg['resource_expanded_width']);height=min(area.height(),cfg['resource_expanded_height'])
        x=center.x()-width//2;y=center.y()-height//2
        if vertical:
            x=bar.right()+1 if bar.center().x()<screen.geometry().center().x() else bar.left()-width
        else:
            y=bar.bottom()+1 if bar.center().y()<screen.geometry().center().y() else bar.top()-height
        return QRect(max(area.left(),min(x,area.right()-width+1)),max(area.top(),min(y,area.bottom()-height+1)),width,height)

    def placement_changed(self):
        if not self.service.cfg['resource_capsule_taskbar']:self.sync_taskbar()
        self.reposition();self.resize_edges.sync();self.update()

    def taskbar_at(self,point):
        if self.service.runtime.dock.preview:return None
        from resource_taskbar import taskbars
        return next((bar for bar in taskbars() if bar['rect'].contains(point)),None)

    def layer(self):
        if self.service.runtime.dock.preview:return
        from window_layers import desktop_layer, is_topmost, shell_owner, owner_of
        hwnd=int(self.winId());top=self.service.cfg['resource_layer']=='top'
        if self.taskbar_slot() is not None:
            from window_layers import set_owner
            from taskbar_input import place_layer
            from platform_services import fullscreen_window
            placement=self.taskbar_placement;bar=placement.slot_bar['hwnd']
            state=(hwnd,'taskbar',bar,placement.layer)
            if self.last_layer!=state or owner_of(hwnd):
                if set_owner(hwnd,0) and place_layer(hwnd,bar,placement.layer,cover=fullscreen_window() if top else None):self.last_layer=state
            return
        owner=0 if top else shell_owner()
        state=(hwnd,top,owner)
        if self.last_layer!=state or is_topmost(hwnd)!=top or owner_of(hwnd)!=owner:
            if desktop_layer(hwnd,top,owner):self.last_layer=state
    def raise_if_top(self):
        if self.taskbar_slot() is not None:
            self.restore_input_layer();return
        if self.service.cfg['resource_layer']=='top' and not self.service.runtime.dock.preview:
            from window_layers import restack
            restack(int(self.winId()),-1)

    def restore_input_layer(self,cover=None):
        if (self.press is not None or not self.isVisible() or self.taskbar_slot() is None
                or self.service.runtime.dock.preview):return
        from taskbar_input import place_layer,restore_input_layer
        placement=self.taskbar_placement;hwnd=int(self.winId());bar=placement.slot_bar['hwnd']
        if placement.layer=='bottom':place_layer(hwnd,bar,'bottom')
        else:
            from platform_services import fullscreen_window
            restore_input_layer(hwnd,bar,cover=fullscreen_window() if cover is None else cover,
                                transparent=passthrough_enabled(self.service.cfg,'resource'))

    def refresh(self):
        self._compact_cache=None
        cfg=self.service.cfg;self.values=display_values(self.service)
        tips=[label+'  '+value+(' · '+tip if tip else '') for _,label,value,tip in self.values]
        if self.service.deck:
            from resource_quota import amount_label, quota_text
            for row in self.service.deck.providers:
                quotas = [amount_label(q).replace(' · 已用', '')+' '+quota_text(q) for q in row.get('quotas', [])]
                tips.append(row['name']+' · '+('; '.join(quotas) or row.get('status','未连接')))
            track=self.service.deck.media.get('track') or {}
            if track:tips.append(track.get('title','')+' · '+track.get('artist',''))
        if cfg['resource_traffic']:
            from resource_traffic import amount
            data=self.service.latest.get('traffic') or {}
            for key,name in [('day','今日'),('month','本月'),('year','本年')]:
                if key in data:tips.append(name+'流量：↓ '+amount(data[key][0])+'  ↑ '+amount(data[key][1])+'  合计 '+amount(sum(data[key])))
        reminder_labels={'agenda':'日程提醒','battery':'电量低','water':'喝水提醒','focus':'专注',
                         'rest':'休息','focus_done':'专注','rest_done':'休息','paused':'已暂停'}
        tips.extend(reminder_labels[kind]+' '+value for kind,value in self.service.reminders())
        if self.service.compact:
            from resource_compact import status_values
            tips.extend(label+' '+value for _,label,value,_ in status_values(self.service))
            tips.append('滚轮切换读数，点击展开')
        self.setToolTip('');self.setAccessibleName('\n'.join(tips) or '资源胶囊 · 点击展开')
        if not self.service.compact:
            if not self.page_enabled(self.page_key):self.page_key=self.first_page()
            self.scroll.setVisible(self.page_key=='resources')
            self.empty_page.setVisible(self.page_key is None)
            if self.page_key and self.page_key!='resources':self.view(self.page_key).show();self.view(self.page_key).refresh()
            for key in tuple(self.page_buttons)[1:]:
                view=getattr(self,'_'+key+'_view')
                if view and key!=self.page_key:view.hide()
        if not self.service.compact and self.page_key=='resources':self.refresh_dashboard()
        for key,btn in self.page_buttons.items():
            enabled=self.page_enabled(key)
            btn.setVisible(not self.service.compact and enabled);btn.setChecked(key==self.page_key)
        self.layout_page_buttons()
        if self.service.compact:self.reposition();self.sync_animation()
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
        for key in self.service.cfg['resource_component_order']:
            btn=self.page_buttons[key]
            if not self.page_enabled(key):continue
            width=max(44,len(btn.text())*11+10)
            btn.setGeometry(x,0,width,24);x+=width+2
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
                         self.liquid.radii(radius))
        from resource_compact import paint_halo,paint_compact,paint_ball_reminder
        paint_halo(self,p)
        ink=QColor(c['ink']);accent=QColor(metric_colors(self.service)['cpu']);font=QFont(self.font());font.setPixelSize(13)
        if compact and (self.width()<70 or (cfg['resource_fold']=='ball')):
            if cfg['resource_face']:
                self.liquid.paint_face(p,rect.center(),max(20,self.width()-12))
            else:
                q=rect.center();p.setPen(QPen(accent,2,Qt.SolidLine,Qt.RoundCap))
                for n,h in enumerate((7,14,10)):p.drawLine(QPointF(q.x()-5+5*n,q.y()+6),QPointF(q.x()-5+5*n,q.y()+6-h))
            paint_ball_reminder(self,p,rect)
            return
        if not compact:
            if self.nav.isVisible():
                fill=QColor(c['hover']);fill.setAlpha(25)
                p.setPen(Qt.NoPen);p.setBrush(fill)
                p.drawRoundedRect(QRectF(self.nav.geometry()).adjusted(0,0,1,0),6,6)
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
        scroll = None
        if self.compact_scroll:
            previous, since, direction = self.compact_scroll
            progress = (time.monotonic() - since) / COMPACT_SCROLL_SECONDS
            if progress < 1:
                scroll = previous, max(0., progress), direction
        paint_compact(self,p,scroll)
        return

    def wheelEvent(self,event):
        if self.service.compact and event.angleDelta().y():
            self.shift_compact_page(1 if event.angleDelta().y()<0 else -1)
            event.accept()
        else:event.ignore()
    def enterEvent(self,event):
        self.outside_since = None
        if self.service.cfg['resource_expand_mode']=='hover' and not passthrough_enabled(self.service.cfg,'resource') and self.service.compact:self.enter_timer.start()
        super().enterEvent(event)
    def expand_hover(self):
        cursor=QCursor.pos()
        if self.service.cfg['resource_expand_mode']=='hover' and not passthrough_enabled(self.service.cfg,'resource') and self.press is None and not self.liquid.landing and self.isVisible() and self.geometry().contains(cursor):
            self.expand_from(self.mapFromGlobal(cursor),automatic=True)

    def expand_from(self,point,automatic=False):
        badges=self.service.reminders()
        icon_only=self.width()<70 or self.service.cfg['resource_fold']=='ball'
        if badges and icon_only:
            kind=badges[0][0]
        elif not icon_only:
            kind=next((kind for kind,rect in zip(self.reminder_kinds,self.reminder_bounds) if rect.contains(QPointF(point))),None)
        else:kind=None
        if kind:
            target={'agenda':'agenda','battery':'resources'}.get(kind,'pomodoro')
        else:
            row=next((key for key,rect in zip(getattr(self,'compact_shown',()),getattr(self,'compact_bounds',()))
                      if rect.contains(QPointF(point))),None) if not icon_only else None
            if row is None and not icon_only:
                row=next((key for key,rect in self.status_bounds.items() if rect.contains(QPointF(point))),None)
            target=COMPACT_PAGES.get(row)
        if target and self.service.detached(target):
            if not automatic:self.service.open_component(target)
            return
        if self.service.fold(False,automatic=automatic) and not self.service.compact and target and self.page_enabled(target):
            self.select_page(target)
    def leaveEvent(self,event):
        self.enter_timer.stop()
        super().leaveEvent(event)
    def fold_idle(self):
        # Native leave events can be lost when a popup or mouse grab takes over.
        cursor=QCursor.pos();slot=self.taskbar_slot()
        if (self.press is not None or self.tab_drag is not None or self.liquid.landing or self.geometry().contains(cursor)
                or (slot is not None and slot.contains(cursor))
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
        if self.moved:
            target=self.origin+delta
            if self.pos()!=target:self.move(target);self.liquid.moved()
            event.accept()
    def mouseReleaseEvent(self,event):
        if event.button()!=Qt.LeftButton or self.press is None:return
        self.mouseMoveEvent(event)
        self.press=None
        self.liquid.released()
        try:self.finish_move(event)
        finally:
            if self.taskbar_placement:self.taskbar_placement.resume()
            if self.moved:self.update()

    def finish_move(self,event):
        if not self.moved:
            if self.service.compact:self.expand_from(event.pos())
            return
        bar=self.taskbar_at(event.globalPos())
        if bar:
            center=self.geometry().center()
            self.reposition()
            self.ensure_taskbar_placement().offer(bar,center)
            return
        if self.taskbar_slot() is not None:
            self.reposition();return
        if self.liquid.drop(event.globalPos()):return
        rect=QRect(self.geometry())
        screen=QApplication.screenAt(event.globalPos()) or QApplication.primaryScreen();area=screen.availableGeometry()
        rect.moveLeft(max(area.left(),min(rect.x(),area.right()-rect.width()+1)))
        rect.moveTop(max(area.top(),min(rect.y(),area.bottom()-rect.height()+1)))
        if self.pos()!=rect.topLeft():self.move(rect.topLeft())
        if not self.service.set_options(resource_edge='free',resource_layout=capture(list(rect.getRect()),screen_records())):self.reposition()
    def contextMenuEvent(self,event):
        self.enter_timer.stop();self.outside_since=None;menu=AlignedMenu(self);cfg=self.service.cfg
        menu.addAction('展开详情' if self.service.compact else '收起胶囊',lambda:self.service.fold(not self.service.compact))
        opening=menu.addMenu('展开后默认页面')
        for key,label in OPEN_PAGES.items():
            item=opening.addAction(label);item.setCheckable(True);item.setChecked(cfg['resource_open_page']==key)
            item.setEnabled(key=='last' or self.page_enabled(key))
            item.triggered.connect(lambda checked,key=key:self.service.set_options(resource_open_page=key))
        for name,layer in [('置顶显示','top'),('置于底层','bottom')]:
            item=menu.addAction(name);item.setCheckable(True);item.setChecked(cfg['resource_layer']==layer)
            item.triggered.connect(lambda checked,layer=layer:self.service.set_options(resource_layer=layer))
        passing=menu.addAction('鼠标穿透');passing.setCheckable(True);passing.setChecked(cfg['resource_click_through'])
        passing.triggered.connect(lambda on:self.service.set_options(resource_click_through=on))
        pin=menu.addAction('固定胶囊到任务栏');pin.setCheckable(True);pin.setChecked(cfg['resource_capsule_taskbar'])
        pin.triggered.connect(lambda on:self.service.set_options(resource_capsule_taskbar=on,
                                                               resource_collapsed=on or cfg['resource_collapsed']))
        bar=menu.addAction('任务栏监控');bar.setCheckable(True);bar.setChecked(cfg['resource_taskbar'])
        bar.triggered.connect(lambda enabled:self.service.set_options(resource_taskbar=enabled))
        auto=menu.addAction('鼠标离开自动收起');auto.setCheckable(True);auto.setChecked(cfg['resource_auto_hide'])
        auto.triggered.connect(lambda on:self.service.set_options(resource_auto_hide=on))
        edge=menu.addAction('屏幕边缘吸附');edge.setCheckable(True);edge.setChecked(cfg['resource_edge_snap'])
        edge.setEnabled(cfg['card_snap']);edge.triggered.connect(lambda on:self.service.set_options(resource_edge_snap=on))
        menu.addSeparator();menu.addAction('资源显示设置…',self.service.settings)
        menu.addAction('关闭资源胶囊',lambda:self.service.set_options(resource_enabled=False))
        try:menu.exec_(event.globalPos())
        finally:menu.deleteLater()
    def closeEvent(self,event):
        event.ignore();self.service.set_options(resource_enabled=False)
    def hideEvent(self,event):
        self._compact_surface=None
        self.clear_tab_drop()
        self.settle_compact_scroll()
        self.animation.stop();self.clock_tick.stop();self.rotate.stop()
        self.wallpaper_timer.stop()
        self.enter_timer.stop();self.auto_fold_timer.stop();self.outside_since=None
        if hasattr(self,'liquid'):self.liquid.hide()
        if self.service.extras and not self.service.detached('weather'):self.service.extras.pause()
        super().hideEvent(event)
    def showEvent(self,event):
        super().showEvent(event)
        self.last_layer=None
        self.sync_auto_fold()
        if self.colors:
            self.sync_animation();self.liquid.sync();self.sync_wallpaper()
        if self.service.extras:self.service.extras.sync()
    def dispose(self):
        if self.taskbar_placement:
            placement,self.taskbar_placement=self.taskbar_placement,None;placement.close()
        self.liquid.close()
        self.animation.stop();self.clock_tick.stop();self.rotate.stop()
        self.enter_timer.stop();self.auto_fold_timer.stop();self.glass.clear();self.hide();self.deleteLater()
