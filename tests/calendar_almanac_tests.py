"""Check the card's date boundaries, shipped artwork, and compact reminder."""
from datetime import date, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch


def dates_and_assets():
    from calendar_almanac import ART, ASSETS, CIVIL_HOLIDAYS, FIRST_DAY, LAST_DAY, almanac, edition, next_civil_holiday, next_festival, term_dates, until_rotation, verse_index
    assert len(ART)==36+len(CIVIL_HOLIDAYS) and all(len(set(art.verses))==4 for art in ART.values())
    assert len({line for art in ART.values() for line in art.verses if line})==4*len(ART)
    periods=[datetime(2026,11,19,8,m) for m in (0,10,20,30,40)]
    assert [edition(t) for t in periods]==[0,1,0,1,0] and [verse_index(t) for t in periods]==[0,1,2,3,0]
    files=[ASSETS/'pictures'/f'{art.key}{suffix}.jpg' for art in ART.values() for suffix in ('','-print')]
    assert len({sha256(path.read_bytes()).digest() for path in files})==2*len(ART)
    assert all(len(term_dates(y))==24 for y in range(1901,2101))
    assert almanac(FIRST_DAY).term=='冬至' and almanac(LAST_DAY).next_term=='小寒'
    assert almanac(FIRST_DAY-timedelta(days=1)) is None
    winter=almanac(date(2026,11,7))
    for i in range(15):
        model=almanac(winter.day+timedelta(days=i))
        assert (model.term,model.card().key,model.next_term,model.days_left)==('立冬',winter.card().key,'小雪',15-i)
        assert model.term_today==(i==0)
    assert almanac(date(2026,11,19)).lunar=='十月十一'
    snow=almanac(date(2026,11,22))
    assert snow.term_today and (snow.card().name,snow.next_term,snow.days_left)==('小雪','大雪',15)
    assert almanac(date(2025,1,28)).festival=='除夕' and next_festival(date(2025,1,28))==('春节',1)
    assert almanac(date(2025,7,27)).lunar=='闰六月初三' and not almanac(date(2025,7,27)).festival
    mixed=almanac(date(2026,3,20))
    assert (mixed.festival,mixed.card().name,mixed.card(True).name,mixed.badge())==('龙抬头','龙抬头','春分','龙抬头 · 春分')
    mid=almanac(date(2026,9,25))
    assert mid.card().name=='中秋节' and '婵娟' in mid.card().verses[0]
    assert {almanac(date(2026,1,1)+timedelta(days=i)).festival for i in range(365)} >= {
        '春节','元宵节','龙抬头','端午节','七夕','中元节','中秋节','重阳节','腊八节','北方小年','南方小年','除夕'}
    for (month, number), art in CIVIL_HOLIDAYS.items():
        day = date(2026,month,number)
        assert next_civil_holiday(day-timedelta(days=1)) == (art.name,1)
        assert almanac(day).card() == art and almanac(day).civil_countdown() == '今日'+art.name
    assert next_civil_holiday(date(2026,12,31)) == ('元旦',1)
    assert next_civil_holiday(date(2026,5,1)) == ('青年节',3)
    assert almanac(date(2026,11,21)).civil_countdown() == '距元旦 41 天'
    double = almanac(date(2031,1,1))
    assert double.events == ('元旦','腊八节') and [double.card(i).name for i in range(3)] == ['元旦','腊八节','元旦']
    boundary=datetime(2026,11,19,23,59,59,990000)
    assert 10<=until_rotation(boundary)<=11 and edition(boundary)==1 and edition(boundary+timedelta(milliseconds=10))==0


def render(dock, cfg, output):
    from PyQt5.QtCore import Qt, QRectF
    from PyQt5.QtGui import QImage, QPainter
    from desktop_clock import draw_clock
    folder=Path(output);folder.mkdir(parents=True,exist_ok=True)
    for name, day, size, minute, term in [
            ('normal',date(2026,11,19),(360,235),0,False),('snow',date(2026,11,22),(360,235),0,False),
            ('moon',date(2026,9,25),(360,235),0,False),('moon-print',date(2026,9,25),(360,235),10,False),
            ('national-day',date(2026,10,1),(360,235),0,False),('national-day-print',date(2026,10,1),(360,235),10,False),
            ('overlap-festival',date(2026,3,20),(260,230),0,False),('overlap-term',date(2026,3,20),(260,230),0,True),
            ('clock-min',date(2026,11,19),(160,100),10,False),('portrait',date(2026,6,19),(260,360),0,False)]:
        image=QImage(*size,QImage.Format_ARGB32_Premultiplied);image.fill(Qt.transparent)
        painter=QPainter(image)
        try:
            from calendar_almanac_face import _line
            with patch('calendar_almanac_face._line',wraps=_line) as line:
                draw_clock(painter,QRectF(0,0,*size),dock,dict(cfg, _now=datetime(2026,1,1,8,minute),
                           _almanac_date=day,_almanac_art=term,_almanac_controls='clock' if name=='clock-min' else ''),'almanac')
                civil = next(call for call in line.call_args_list if call.args[2].startswith('公历'))
                assert civil.args[1].height()>=10 and civil.args[1].bottom() < line.call_args.args[1].top()
        finally:painter.end()
        assert image.save(str(folder/f'almanac-{name}.png'))


def compact_cases(service):
    from calendar_almanac import almanac
    from resource_compact import compact_badges
    from resource_options import DEFAULTS
    assert DEFAULTS['resource_alert_almanac'] is True
    for when,label,special in [(date(2026,11,19),'小雪 3天',False),(date(2026,11,22),'小雪',True),
                               (date(2026,9,25),'中秋节',True),(date(2026,3,20),'龙抬头 · 春分',True)]:
        with patch('calendar_almanac.almanac',return_value=almanac(when)):
            with patch.dict(service.cfg,resource_alert_almanac=True):
                badges,count=compact_badges(service)
                assert [v for k,v in badges if k=='almanac']==[label]
                assert (('almanac',label) in badges[:count])==special
            with patch.dict(service.cfg,resource_alert_almanac=False):
                assert 'almanac' not in dict(compact_badges(service)[0])


def check_badge_expansion(service, app, automatic=False):
    from PyQt5.QtCore import QEvent, QPointF, Qt
    from PyQt5.QtGui import QMouseEvent
    from PyQt5.QtWidgets import QMenu

    assert service.fold(True)
    app.processEvents()
    window = service.window
    window.grab()
    if service.cfg['resource_fold'] == 'ball' or window.width() < 70:
        assert service.reminders()[0][0] == 'almanac'
        point = window.rect().center()
    else:
        index = window.reminder_kinds.index('almanac')
        point = window.reminder_bounds[index].center().toPoint()
    page = service.cfg['resource_open_page']
    if page == 'last':
        page = window.page_key
    elif not window.page_enabled(page):
        page = window.first_page()
    with patch.object(service, 'fold', wraps=service.fold) as fold, patch.object(QMenu, 'popup') as popup:
        if automatic:
            window.expand_from(point, automatic=True)
        else:
            screen_point = QPointF(window.mapToGlobal(point))
            for event, buttons in ((QEvent.MouseButtonPress, Qt.LeftButton), (QEvent.MouseButtonRelease, Qt.NoButton)):
                app.sendEvent(window, QMouseEvent(event, QPointF(point), screen_point, Qt.LeftButton, buttons, Qt.NoModifier))
        fold.assert_called_once_with(False, automatic=automatic)
        assert not service.compact and window.detail.isVisible() and window.page_key == page
        popup.assert_not_called()
