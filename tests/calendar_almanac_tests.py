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
    assert (mixed.festival,mixed.card().name,mixed.card(True).name)==('龙抬头','龙抬头','春分')
    assert mixed.badge_labels()[:2] == ('春分','龙抬头')
    mid=almanac(date(2026,9,25))
    assert mid.card().name=='中秋节' and '婵娟' in mid.card().verses[0]
    assert {almanac(date(2026,1,1)+timedelta(days=i)).festival for i in range(365)} >= {
        '春节','元宵节','龙抬头','上巳节','端午节','七夕','中元节','中秋节','重阳节','寒衣节','下元节','腊八节','北方小年','南方小年','除夕'}
    for (month, number), art in CIVIL_HOLIDAYS.items():
        day = date(2026,month,number)
        assert next_civil_holiday(day-timedelta(days=1)) == (art.name,1)
        assert almanac(day).card() == art and almanac(day).civil_countdown() == '今日'+art.name
    assert next_civil_holiday(date(2026,12,31)) == ('元旦',1)
    assert next_civil_holiday(date(2026,5,1)) == ('青年节',3)
    assert almanac(date(2026,11,21)).civil_countdown() == '距感恩节 5 天'
    for name, when in [('母亲节',date(2026,5,10)), ('母亲节',date(2027,5,9)),
                       ('父亲节',date(2026,6,21)), ('父亲节',date(2027,6,20)),
                       ('教师节',date(2026,9,10)), ('情人节',date(2026,2,14)), ('圣诞节',date(2026,12,25))]:
        eve, today = almanac(when-timedelta(days=1)), almanac(when)
        assert next_civil_holiday(eve.day) == (name,1)
        assert name.removesuffix('节') in today.badge_labels()
        assert today.card().name == name and today.civil_countdown() == '今日'+name
        assert (ASSETS/'pictures'/f'{today.card().key}.jpg').is_file()
    from calendar_details import civil_festivals, info
    from compact_clock import date_lines
    overlap = almanac(date(2024,5,12))
    assert civil_festivals(overlap.day) == ('护士节','母亲节')
    assert next_civil_holiday(overlap.day-timedelta(days=1)) == ('护士节、母亲节',1)
    assert [overlap.card(i).name for i in range(2)] == ['护士节','母亲节']
    assert overlap.badge_labels()[:2] == ('护士','母亲')
    assert info(overlap.day,{})['name']=='护士节、母亲节'
    assert date_lines(overlap.day,'%m/%d',False,False,True)[1:] == overlap.civil_names
    assert almanac(date(2026,2,17)).badge() == '新春'
    assert almanac(LAST_DAY).badge_labels() == ('小寒5天','元旦1天')
    double = almanac(date(2031,1,1))
    assert double.events == ('元旦','腊八节') and [double.card(i).name for i in range(3)] == ['元旦','腊八节','元旦']
    boundary=datetime(2026,11,19,23,59,59,990000)
    assert 10<=until_rotation(boundary)<=11 and edition(boundary)==1 and edition(boundary+timedelta(milliseconds=10))==0


def render(dock, cfg, output):
    from calendar_almanac import almanac
    from PyQt5.QtCore import Qt, QRectF
    from PyQt5.QtGui import QImage, QPainter
    from desktop_clock import draw_clock
    folder=Path(output);folder.mkdir(parents=True,exist_ok=True)
    for name, day, size, minute, term in [
            ('normal',date(2026,11,19),(360,235),0,False),('snow',date(2026,11,22),(360,235),0,False),
            ('moon',date(2026,9,25),(360,235),0,False),('moon-print',date(2026,9,25),(360,235),10,False),
            ('national-day',date(2026,10,1),(360,235),0,False),('national-day-print',date(2026,10,1),(360,235),10,False),
            ('mother',date(2026,5,10),(360,235),0,False),
            ('overlap-festival',date(2026,3,20),(260,230),0,False),('overlap-term',date(2026,3,20),(260,230),0,True),
            ('clock-min',date(2026,11,19),(160,100),10,False),('portrait',date(2026,6,19),(260,360),0,False),
            ('portrait-narrow',date(2026,11,21),(216,254),10,False)]:
        image=QImage(*size,QImage.Format_ARGB32_Premultiplied);image.fill(Qt.transparent)
        painter=QPainter(image)
        try:
            from calendar_almanac_face import _line
            with patch('calendar_almanac_face._line',wraps=_line) as line:
                draw_clock(painter,QRectF(0,0,*size),dock,dict(cfg, _now=datetime(2026,1,1,8,minute),
                           _almanac_date=day,_almanac_art=term,_almanac_controls='clock' if name=='clock-min' else 'calendar',
                           _almanac_switch_width=74 if name.startswith('overlap-') else 0),'almanac')
                labels = {call.args[2]: call.args[1] for call in line.call_args_list}
                civil = labels[almanac(day).civil_countdown()]
                assert not any(value.startswith('公历') for value in labels)
                assert civil.height()>=10 and civil.bottom() < line.call_args.args[1].top()
                boxes = [call.args[1] for call in line.call_args_list]
                assert all(QRectF(0,0,*size).contains(box) for box in boxes)
                assert all(before.bottom() <= after.top()+.001 for before, after in zip(boxes, boxes[1:]))
        finally:painter.end()
        assert image.save(str(folder/f'almanac-{name}.png'))


def compact_cases(service):
    from calendar_almanac import almanac
    from resource_compact import compact_badges
    from resource_options import DEFAULTS
    assert DEFAULTS['resource_alert_almanac'] is True
    for when,labels,special in [
            (date(2026,11,27),('大雪10天','腊八49天','平安夜27天'),False),
            (date(2026,11,22),('小雪','下元1天','感恩4天'),True),
            (date(2026,9,25),('中秋','国庆6天','寒露13天'),True),
            (date(2026,5,10),('母亲','小满11天','端午40天'),True),
            (date(2024,5,12),('护士','母亲','小满8天','端午29天'),True)]:
        with patch('calendar_almanac.almanac',return_value=almanac(when)):
            with patch.dict(service.cfg,resource_alert_almanac=True):
                for page, label in enumerate((*labels,labels[0])):
                    badges,count=compact_badges(service,page)
                    assert [v for k,v in badges if k=='almanac']==[label]
                    assert (('almanac',label) in badges[:count])==special
            with patch.dict(service.cfg,resource_alert_almanac=False):
                assert 'almanac' not in dict(compact_badges(service)[0])


def check_badge_rotation(window, output, checks):
    from PyQt5.QtCore import QPoint, QPointF, Qt
    from PyQt5.QtGui import QWheelEvent
    from PyQt5.QtWidgets import QApplication
    from calendar_almanac import almanac
    from capsule_order import configured_items
    from resource_compact import plan, text, visible_component_count
    from resource_options import ALMANAC_CATEGORIES, almanac_categories

    service, cfg = window.service, window.service.cfg
    original_size, turns, pages = window.size(), window.page_turns, window.component_pages.copy()
    day = almanac(date(2026,11,27))
    expected = ('大雪10天','腊八49天','平安夜27天')
    weather = ('weather','武清区','4℃',dict(temperature=4,code=2))
    readings = [('cpu','CPU','18%',''),('memory','内存','46%',''),('traffic','今日流量','2 GB',''),weather]
    try:
        with patch.dict(cfg, resource_alert_almanac=True,resource_almanac_term=True,resource_almanac_lunar=True,
                        resource_almanac_civil=True,resource_almanac_interval=7,resource_compact_rotate_interval=9,
                        resource_compact_rotate_left=False,resource_compact_rotate_center=False,resource_compact_rotate_right=False,
                        resource_clock=False,resource_mail=False,resource_face=True,resource_runner_enabled=False,
                        resource_compact_metrics=['cpu','memory','traffic'],resource_compact_order=[],resource_compact_pinned=[],
                        motion_enabled=False), patch.object(service,'indicators',None), patch.object(window,'underMouse',return_value=False), \
                patch('resource_compact.compact_values',return_value=readings) as values, patch('calendar_almanac.almanac',return_value=day):
            resources = window.component_timers['resources']
            holidays = window.component_timers['alert_almanac']
            for shape,zone in [('pill','left'),('bar','center'),('pill','right')]:
                cfg.update(resource_fold=shape,resource_compact_zones={} if zone=='left' else {'alert_almanac':zone})
                window.resize(480,35);window.component_pages.update(resources=0,alert_almanac=0)
                window.offset=0;window._compact_cache=None;window.sync_animation()
                assert resources.isActive() and resources.interval()==9000 and holidays.isActive() and holidays.interval()==7000
                assert not window.rotate.isActive() and window.clock_tick.isActive()
                bounds = []
                for index,label in enumerate((*expected,expected[0])):
                    window._compact_surface=None
                    with patch('resource_compact.text',wraps=text) as draw:
                        frame = window.grab()
                    title,countdown=day.badge_lines()[label]
                    painted={call.args[2]:call.args for call in draw.call_args_list}
                    for name,reference in ((title,'武清区'),(countdown,'4℃')):
                        line,other=painted[name],painted[reference]
                        assert line[1].top()==other[1].top() and line[1].height()==other[1].height() and line[4:]==other[4:]
                    assert painted[title][1].bottom()==painted[countdown][1].top()
                    assert set(window.compact_shown)=={'cpu','traffic','weather'}
                    bounds.append(window.reminder_bounds[window.reminder_kinds.index('almanac')])
                    assert bounds[-1].height()==window.compact_bounds[window.compact_shown.index('weather')].height()
                    if zone=='center' and index<3:
                        assert frame.save(str(Path(output)/f'almanac-capsule-{index+1}.png'))
                    if index<3:holidays.timeout.emit()
                assert all(box==bounds[0] for box in bounds)
                resources.timeout.emit();window.grab()
                assert set(window.compact_shown)=={'memory','traffic','weather'} and window.offset==0
                assert ('almanac',expected[0]) in [chip[:2] for chip in plan(window,window.width())['routine_badges']]
                for rect,key in ((bounds[0],'alert_almanac'),(window.compact_bounds[window.compact_shown.index('memory')],'resources')):
                    before=window.component_pages.copy()
                    point=rect.center()
                    wheel=QWheelEvent(point,QPointF(window.mapToGlobal(point.toPoint())),QPoint(),QPoint(0,-120),
                                      Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False)
                    QApplication.sendEvent(window,wheel);window.grab()
                    assert wheel.isAccepted() and window.offset==0
                    assert [k for k in before if before[k]!=window.component_pages[k]]==[key]
            for mask in range(8):
                selected=[]
                for index,kind in enumerate(ALMANAC_CATEGORIES):
                    enabled=bool(mask & (1<<index))
                    cfg['resource_almanac_'+kind]=enabled
                    if enabled:selected.append(expected[index])
                window._compact_cache=None;window.sync_rotation()
                assert list(day.badge_labels(almanac_categories(cfg)))==selected
                assert holidays.isActive()==(len(selected)>1)
                assert ('alert_almanac' in configured_items(cfg))==bool(selected)
            for rows,count in [(readings[1:],1),(readings[2:],0),(readings,2)]:
                values.return_value=rows;window._compact_cache=None;window.sync_rotation();window.grab()
                assert resources.isActive()==(count>1)
                assert len(set(window.compact_shown)&{'cpu','memory'})==min(count,1) and 'traffic' in window.compact_shown
            cfg.update(resource_face=False,resource_compact_zones={'resources':'left','traffic':'center','alert_almanac':'right'},
                       resource_almanac_term=True,resource_almanac_civil=True)
            window.resize(96,35);window.offset=0;window._compact_cache=None
            visits={}
            for page in range(len(plan(window,96)['pages'])):
                window.offset=page
                visits[bool(visible_component_count(plan(window,96),'alert_almanac'))]=page
            assert set(visits)=={True,False}
            window.offset=visits[True];window.sync_rotation();assert holidays.isActive()
            with patch.object(holidays,'remainingTime',return_value=2750):
                window.offset=visits[False];window.sync_rotation()
            assert not holidays.isActive()
            window.offset=visits[True];window.sync_rotation()
            assert holidays.isActive() and holidays.interval()==2750
            holidays.timeout.emit();assert holidays.interval()==7000
            with patch('calendar_almanac.almanac',return_value=almanac(date(2026,11,22))):
                cfg.update(resource_fold='pill',resource_almanac_lunar=False,resource_almanac_civil=False,
                           resource_compact_zones={'weather':'left','alert_almanac':'left','traffic':'right'},
                           resource_compact_order=['weather','alert_almanac','traffic','resources'])
                window.offset=0
                for height in (16,20,40):
                    cfg['resource_compact_badge_height']=height
                    window.resize(300,max(35,height+6));window._compact_cache=None
                    with patch('resource_compact.text',wraps=text) as draw:
                        frame=window.grab()
                    drawn={call.args[2]:call.args[1] for call in draw.call_args_list}
                    assert drawn['小雪'].top()==drawn['武清区'].top() and drawn['今天'].bottom()==drawn['4℃'].bottom()
                    assert drawn['小雪'].height()==drawn['今天'].height()==height/2
                    if height==20:assert frame.save(str(Path(output)/'almanac-weather-today.png'))
            cfg.update(resource_almanac_term=False,resource_almanac_lunar=True,resource_compact_badge_height=20)
            window.resize(300,35);window._compact_cache=None
            assert window.grab().save(str(Path(output)/'almanac-weather-countdown.png'))
            assert not day.badge_due(('lunar','civil'))
            assert almanac(date(2026,11,22)).badge_due(('term',))
            assert not almanac(date(2026,11,22)).badge_due(('lunar',))
    finally:
        window.resize(original_size);window.page_turns=turns;window.component_pages.update(pages)
        window._compact_cache=None;window.sync_window()
    checks.append('Independently timed resource and holiday cards in folded pills and bars keep their slots alongside traffic. Verified all eight calendar filters, single-reading idle timers, mixed intervals, and disabled zone paging.')
    checks.append('Holiday names and countdowns match the two weather rows in font size, weight and vertical alignment. Verified the same-day label and tile heights of 16, 20 and 40 pixels.')


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
