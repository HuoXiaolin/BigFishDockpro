"""Independent desktop month calendar with event-driven navigation and daily ticks."""
import datetime
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter,QIcon
from desktop_clock import DesktopClock
from ui_style import button,AlignedMenu


class DesktopCalendar(DesktopClock):
    def __init__(self,runtime):
        now=datetime.date.today();self.view_year=now.year;self.view_month=now.month;self.follow_today=True
        super().__init__(runtime,'calendar')
        self.previous=button('‹',lambda:self.shift_month(-1));self.previous.setParent(self);self.previous.setToolTip('上个月')
        self.today=button('今天',self.go_today);self.today.setParent(self)
        self.next=button('›',lambda:self.shift_month(1));self.next.setParent(self);self.next.setToolTip('下个月')
        self.settings=button('',self.open_settings);self.settings.setParent(self);self.settings.setToolTip('日历设置')
        self.controls=(self.previous,self.today,self.next,self.settings);self.place_controls()

    def place_controls(self):
        if not hasattr(self,'controls'):return
        ink=getattr(self,'_control_ink','#506378')
        key=(ink,self.devicePixelRatioF())
        if key!=getattr(self,'_controls_key',None):
            from glass_panel import category_icon
            self.settings.setIcon(QIcon(category_icon('settings',ink,16,key[1])))
            style='QPushButton {background:transparent;border:0;border-radius:6px;padding:0;color:'+ink+';font-size:13px;font-weight:600;} QPushButton:hover {background:rgba(110,150,180,35);}'
            for control in self.controls:control.setStyleSheet(style)
            self._controls_key=key
        x=self.width()-119
        for control,width in zip(self.controls,(23,38,23,23)):
            control.show();control.setFixedSize(width,24);control.move(x,11);x+=width+2

    def sync(self):
        super().sync();self.place_controls()

    def shift_month(self,direction):
        index=self.view_year*12+self.view_month-1+direction;year,month=divmod(index,12)
        if not 1<=year<=9999:return False
        self.view_year,self.view_month=year,month+1;self.follow_today=False;self.update();return True

    def go_today(self):
        now=datetime.date.today();self.view_year,self.view_month=now.year,now.month;self.follow_today=True;self.update()

    def update_time(self):
        if not self.isVisible() or self.closed:return
        now=datetime.datetime.now()
        if self.follow_today:self.view_year,self.view_month=now.year,now.month
        self.update();tomorrow=datetime.datetime.combine(now.date()+datetime.timedelta(days=1),datetime.time())
        self.tick.start(max(1000,round((tomorrow-now).total_seconds()*1000)))

    def paintEvent(self,event):
        from calendar_markers import countdowns
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        self.paint_resize_targets(painter)
        self.paint_face(painter,'calendar_card',_calendar_year=self.view_year,_calendar_month=self.view_month,
                        _calendar_events=self.runtime.resources.calendar_entries(),
                        _calendar_countdowns=countdowns(self.dock.cfg))

    def build_menu(self):
        menu=AlignedMenu(self);menu.addAction('回到今天').triggered.connect(self.go_today);menu.addAction('日历设置…').triggered.connect(self.open_settings)
        if self.parentWidget() is None:
            lock=menu.addAction('锁定位置与大小');lock.setCheckable(True);lock.setChecked(self.option('locked'));lock.triggered.connect(self.set_locked)
        menu.addSeparator();menu.addAction('隐藏日历').triggered.connect(lambda:self.set_enabled(False));return menu
