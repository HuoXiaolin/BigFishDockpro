"""Independent desktop month calendar with event-driven navigation and daily ticks."""
import datetime
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter,QIcon,QFontMetrics
from calendar_almanac_face import almanac_padding, calendar_controls
from desktop_clock import DesktopClock
from ui_style import button,AlignedMenu


class DesktopCalendar(DesktopClock):
    def __init__(self,runtime):
        now=datetime.date.today();self.view_year=now.year;self.view_month=now.month;self.follow_today=True
        self.view_day=now;self.art_choice=0
        super().__init__(runtime,'calendar')
        self.previous=button('‹',lambda:self.navigate(-1));self.previous.setParent(self)
        self.today=button('今天',self.go_today);self.today.setParent(self)
        self.next=button('›',lambda:self.navigate(1));self.next.setParent(self)
        self.settings=button('',self.open_settings);self.settings.setParent(self);self.settings.setToolTip('日历设置')
        self.other_art=button('',self.switch_art);self.other_art.setParent(self)
        self.controls=(self.previous,self.today,self.next,self.settings);self.place_controls()

    def place_controls(self):
        if not hasattr(self,'controls'):return
        ink=getattr(self,'_control_ink','#506378')
        key=(ink,self.devicePixelRatioF())
        if key!=getattr(self,'_controls_key',None):
            from glass_panel import category_icon
            self.settings.setIcon(QIcon(category_icon('settings',ink,16,key[1])))
            style='QPushButton {background:transparent;border:0;border-radius:6px;padding:0;color:'+ink+';font-size:13px;font-weight:600;} QPushButton:hover {background:rgba(110,150,180,35);}'
            for control in (*self.controls,self.other_art):control.setStyleSheet(style)
            self._controls_key=key
        seasonal=self.option('style')=='almanac'
        widths=calendar_controls(self.width()-2) if seasonal else (23,38,23,23)
        x=self.width()-sum(widths)-12
        for control,width in zip(self.controls,widths):
            control.show();control.setFixedSize(width,24);control.move(x,11);x+=width+2
        self.previous.setToolTip('前一天' if seasonal else '上个月');self.next.setToolTip('后一天' if seasonal else '下个月')
        if seasonal:
            from calendar_almanac import almanac,FIRST_DAY,LAST_DAY
            model=almanac(self.view_day)
            self.previous.setEnabled(self.view_day>FIRST_DAY);self.next.setEnabled(self.view_day<LAST_DAY)
            if model and len(model.events)>1:
                self.other_art.setText('看'+model.card(self.art_choice+1).name+' ›')
                pad=round(almanac_padding(self.width()-2,self.height()-2))+1
                width=QFontMetrics(self.other_art.font()).horizontalAdvance(self.other_art.text())+10
                self.other_art.setFixedSize(width,22)
                self.other_art.move(self.width()-pad-width,self.height()-pad-22)
                self.other_art.show();return
        else:
            self.previous.setEnabled(True);self.next.setEnabled(True)
        self.other_art.hide()

    def switch_art(self):
        self.art_choice+=1
        self.place_controls();self.update()

    def navigate(self,direction):
        if self.option('style')!='almanac':return self.shift_month(direction)
        from calendar_almanac import FIRST_DAY,LAST_DAY
        day=self.view_day+datetime.timedelta(days=direction)
        if not FIRST_DAY<=day<=LAST_DAY:return False
        self.view_day=day;self.view_year,self.view_month=day.year,day.month
        self.follow_today=False;self.art_choice=0;self.place_controls();self.update();return True

    def sync(self):
        if self.option('style')=='almanac':
            from calendar_almanac import FIRST_DAY,LAST_DAY
            self.view_day=max(FIRST_DAY,min(LAST_DAY,self.view_day))
        super().sync();self.place_controls()

    def shift_month(self,direction):
        index=self.view_year*12+self.view_month-1+direction;year,month=divmod(index,12)
        if not 1<=year<=9999:return False
        self.view_year,self.view_month=year,month+1;self.view_day=datetime.date(year,month+1,1)
        self.follow_today=False;self.art_choice=0;self.update();return True

    def go_today(self):
        now=datetime.date.today();self.view_day=now;self.view_year,self.view_month=now.year,now.month
        self.follow_today=True;self.art_choice=0;self.place_controls();self.update()

    def update_time(self):
        if not self.isVisible() or self.closed:return
        now=datetime.datetime.now()
        if self.follow_today and self.view_day!=now.date():
            self.view_day=now.date();self.view_year,self.view_month=now.year,now.month
            self.art_choice=0;self.place_controls()
        if self.option('style')=='almanac':
            from calendar_almanac import until_rotation
            self.update();self.tick.start(until_rotation(now));return
        self.update();tomorrow=datetime.datetime.combine(now.date()+datetime.timedelta(days=1),datetime.time())
        self.tick.start(max(1000,round((tomorrow-now).total_seconds()*1000)))

    def paintEvent(self,event):
        from calendar_markers import countdowns
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        self.paint_resize_targets(painter)
        if self.option('style')=='almanac':
            switch_width=0 if self.other_art.isHidden() else self.other_art.width()+6
            self.paint_face(painter,'almanac',_almanac_date=self.view_day,_almanac_art=self.art_choice,
                            _almanac_controls='calendar',_almanac_switch_width=switch_width)
            return
        self.paint_face(painter,'calendar_card',_calendar_year=self.view_year,_calendar_month=self.view_month,
                        _calendar_events=self.runtime.resources.calendar_entries(),
                        _calendar_countdowns=countdowns(self.dock.cfg))

    def build_menu(self):
        from ui_style import menu_heading
        menu=AlignedMenu(self);menu_heading(menu,'桌面日历')
        menu.addAction('回到今天').triggered.connect(self.go_today);menu.addAction('日历设置…').triggered.connect(self.open_settings)
        menu.addSeparator()
        if self.parentWidget() is None:
            lock=menu.addAction('锁定位置与大小');lock.setCheckable(True);lock.setChecked(self.option('locked'));lock.triggered.connect(self.set_locked)
        menu.addSeparator();menu.addAction('隐藏日历').triggered.connect(lambda:self.set_enabled(False));return menu
