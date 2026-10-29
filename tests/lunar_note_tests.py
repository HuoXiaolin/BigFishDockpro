"""Offline lunar/festival labels, exact holiday dots and transparent note flip."""
import copy,datetime as dt
from pathlib import Path
from PyQt5.QtCore import Qt,QRectF
from PyQt5.QtGui import QPixmap,QPainter,QColor
from PyQt5.QtWidgets import QApplication


def run(api,runtime,output,checks):
    from calendar_details import info,lunar
    from clock_appearance import normalize
    from clock_design import draw
    from clock_options import ClockOptions
    cfg=runtime.dock.cfg;original=copy.deepcopy(cfg);app=QApplication.instance();dialog=None
    try:
        work=normalize({})['work']
        assert info(dt.date(2026,2,17),work)['name']=='春节'
        assert info(dt.date(2026,6,19),work)['name']=='端午节'
        assert info(dt.date(2026,9,25),work)['name']=='中秋节'
        assert info(dt.date(2026,2,16),work)['name']=='除夕'
        assert lunar(dt.date(2023,3,22))==('闰二月','')
        assert lunar(dt.date(2101,1,1))==('','')
        assert {day for day in range(1,32) if info(dt.date(2026,10,day),work)['marker']}=={1,2,3,4,5,6,7,18}
        assert info(dt.date(2026,10,10),work)['makeup'] and not info(dt.date(2026,10,10),work)['marker']
        assert not info(dt.date(2026,10,11),work)['marker']
        class MarkerPainter:
            def __init__(self,painter):self.painter=painter;self.dots=[]
            def __getattr__(self,key):return getattr(self.painter,key)
            def drawEllipse(self,center,rx,ry):self.dots.append(center);return self.painter.drawEllipse(center,rx,ry)
        for size in [(630,300),(320,280),(260,230)]:
            image=QPixmap(*size);image.fill(Qt.transparent);p=QPainter(image);proxy=MarkerPainter(p);labels=[];options=normalize({});options.update(_calendar_year=2026,_calendar_month=10)
            draw('calendar_card',proxy,*size,dt.datetime(2026,10,29),options,QColor('#17394e'),QColor('#526b7b'),QColor('#2f95b8'),lambda box,value,*args:labels.append((box,value)),'09:30','')
            p.end();assert len(proxy.dots)==8 and any(value=='国庆节' for box,value in labels) and any(value=='重阳节' for box,value in labels)
        calendar=runtime.calendar;calendar.set_enabled(True);calendar.view_year,calendar.view_month=2026,10;calendar.follow_today=False;calendar.resize(560,380);app.processEvents();calendar.grab().save(str(Path(output)/'calendar-lunar-holidays.png'))
        dialog=ClockOptions(calendar);dialog.show();dialog.tabs.setCurrentIndex(3);app.processEvents()
        assert dialog.tabs.tabText(3)=='农历与节假日' and 'start' not in dialog.fields and 'rest_dates' not in dialog.fields
        dialog.fields['show_lunar'].setChecked(False);dialog.fields['show_holidays'].setChecked(False);assert dialog.commit()
        assert not cfg['calendar_appearance']['show_lunar'] and not cfg['calendar_appearance']['show_holidays']
        dialog.fields['show_lunar'].setChecked(True);dialog.fields['show_holidays'].setChecked(True);assert dialog.commit();dialog.grab().save(str(Path(output)/'calendar-lunar-settings.png'))
        dialog.reject();dialog.deleteLater();dialog=None
        for style in ('glass','paper','plain'):
            cfg['note_style']=style;identity=runtime.notes.new();note=runtime.notes.windows[identity];note.editor.setPlainText('透明翻页演示\n☐ 检查今日安排');runtime.notes.flush();app.processEvents()
            note.flip_button.click();note.pages.animation.pause();assert note.pages.frames is not None
            assert all(frame.toImage().pixelColor(0,0).alpha()==0 for frame in note.pages.frames)
            for progress in (.2,.5,.8):
                note.pages.advance(progress);app.processEvents();assert note.pages.frames is not None
                note.grab().save(str(Path(output)/('note-flip-'+style+'-'+str(progress)+'.png')))
            note.pages.animation.stop();note.pages.finish();assert note.pages.currentIndex()==1 and note.pages.currentWidget().isVisible()
            note.flip_button.click();note.pages.animation.pause();note.resize(note.width()+10,note.height()+10);app.processEvents();assert note.pages.frames is None
        checks.append('lunar calendars: known CNY/Dragon Boat/Mid-Autumn/Eve dates, leap month and unsupported-year fallback; October holiday dots exactly 1-7 and 18, none on ordinary Sunday or makeup Saturday; three calendar sizes and independent calendar settings flags saved; three note materials have transparent snapshots throughout paused flip phases, resize cancels snapshots cleanly')
    finally:
        if dialog:dialog.reject();dialog.deleteLater()
        cfg.clear();cfg.update(original);api.save_config(cfg);runtime.notes.reload();runtime.calendar.reposition();runtime.apply_settings();app.processEvents()
