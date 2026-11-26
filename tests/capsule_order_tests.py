"""The compact-order editor, saved preferences and native painted hit regions agree."""
import copy
import time
from types import SimpleNamespace
from unittest.mock import patch

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import QApplication, QPushButton


def sort_dialog(options, expected, target=None, *, split=None, accept=True, shot=None):
    errors=[]
    def inspect():
        dialog=QApplication.activeModalWidget()
        try:
            actions={b.text():b for b in dialog.findChildren(QPushButton)}
            def flattened():return [key for keys in dialog.groups().values() for key in keys]
            assert flattened()==expected,(flattened(),expected)
            assert all(view.dragDropMode()==view.DragDrop for view in dialog.lists.values())
            assert not actions['上移'].isEnabled()
            if target:
                groups=dialog.groups()
                if split is not None:
                    from PyQt5.QtCore import QPointF
                    from PyQt5.QtGui import QDropEvent
                    source = next(v for v in dialog.lists.values() if v.selectedItems())
                    destination = next(v for v in dialog.lists.values() if v is not source and not v.count())
                    moved = source.currentItem().data(Qt.UserRole)
                    class Drop(QDropEvent):
                        def source(self):
                            return source
                    mime = source.model().mimeData(source.selectedIndexes())
                    event = Drop(QPointF(4,4),Qt.MoveAction,mime,Qt.LeftButton,Qt.NoModifier)
                    destination.dropEvent(event)
                    assert event.isAccepted() and dialog.groups()[destination.zone]==[moved]
                    assert len(flattened())==len(set(flattened()))==len(expected)
                if split is not None:
                    groups=dict(left=target[:split[0]],center=target[split[0]:split[1]],right=target[split[1]:])
                else:
                    groups={zone:[k for k in target if k in keys] for zone,keys in groups.items()}
                for zone, keys in groups.items():
                    for key in keys:
                        source=next(v for v,entries in dialog.groups().items() if key in entries)
                        if source!=zone:
                            dialog.lists[source].setCurrentRow(dialog.groups()[source].index(key))
                            dialog.location.activated[int].emit(dialog.location.findData(zone))
                for zone, keys in groups.items():
                    view=dialog.lists[zone]
                    for index,key in enumerate(keys):
                        view.setCurrentRow(dialog.groups()[zone].index(key))
                        for _ in range(view.currentRow()-index):actions['上移'].click()
                    assert dialog.groups()[zone]==keys
                assert flattened()==target
            if shot:assert dialog.grab().save(str(shot))
            actions['确定' if accept else '取消'].click()
        except BaseException as problem:
            errors.append(problem)
            if dialog:dialog.reject()
    QApplication.processEvents()
    page=options.tabs.currentWidget()
    sort_button=next(b for b in page.findChildren(QPushButton) if b.text()=='显示顺序…' and b.isVisibleTo(page))
    QTimer.singleShot(0,inspect)
    sort_button.click()
    if errors:raise errors[0]


def check_clocks(api, runtime, app, output, checks):
    from datetime import datetime, timedelta
    from PyQt5.QtCore import QRectF
    from PyQt5.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter
    from compact_clock import clock_fonts, clock_text_height, clock_width, date_lines, draw_clock, headers, lines_at
    from resource_options import COMPACT_CLOCK_FORMATS, compact_text_height, compact_tile_height
    from resource_compact import plan

    dock = runtime.dock
    cfg = dock.cfg
    moment = datetime(2020,10,1,19,43,0)
    forms = COMPACT_CLOCK_FORMATS['seconds'][1]
    upper = date_lines(moment.date(), forms[0], True, True, True)
    assert set(upper)=={'10/01 周四','八月十五','国庆节','中秋节'}, upper
    assert {lines_at(moment+timedelta(seconds=i*6),upper,forms[1])[0] for i in range(4)}==set(upper)
    assert date_lines(moment.date(),forms[0],False,False,False)==('10/01',)
    for seconds in (0,7,28,59):
        now=moment.replace(second=seconds)
        assert lines_at(now,upper,forms[1])[1]==now.strftime('%H:%M:%S')
    # Measure actual glyph pixels, including descenders. Every row stays centered,
    # and the measured side inset belongs to the surface being painted.
    for is_dock in (False,True):
        for height in ((28,36,48) if is_dock else (16,20,24,28,40)):
            width=clock_width(upper, forms[1], height, is_dock)
            caption, primary = clock_fonts(height,is_dock)
            assert caption.weight()==primary.weight()==QFont.Bold
            needed=max([QFontMetricsF(caption).horizontalAdvance(s) for s in upper]+
                       [QFontMetricsF(primary).horizontalAdvance('88:88:88')])
            inset = 6 if is_dock else 2
            assert 2*inset<=width-needed<2*inset+1
            image=QImage(width,height,QImage.Format_ARGB32_Premultiplied)
            image.fill(Qt.transparent)
            p=QPainter(image)
            draw_clock(p,QRectF(0,0,width,height),('八月十五','19:43:56'),QColor('red'),QColor('blue'),is_dock)
            p.end()
            areas=[[],[]]
            for y in range(height):
                for x in range(width):
                    pixel=image.pixelColor(x,y)
                    if pixel.alpha()>50:
                        areas[int(pixel.blue()>pixel.red())].append((x,y))
            assert all(areas)
            assert max(y for x,y in areas[0]) < min(y for x,y in areas[1])
            for area in areas:
                xs,ys=zip(*area)
                assert inset<=min(xs)<=max(xs)<width-inset and 0<=min(ys)<=max(ys)<height,(is_dock,height,area)
                assert abs(min(xs)+max(xs)-(width-1))<=3
            top=min(y for _,y in areas[0]);bottom=max(y for _,y in areas[1])
            assert abs(bottom-top+1-clock_text_height(height,is_dock))<=2 and abs(top+bottom-(height-1))<=2,(is_dock,height,top,bottom)
    original_width,was_visible=dock.extras.width(),dock.isVisible()
    try:
        with patch.dict(cfg, dock_clock=True,dock_clock_seconds=True,dock_clock_weekday=True,dock_clock_lunar=True,dock_clock_festival=True):
            dock.show();dock.reload();app.processEvents()
            upper,lower=dock.extras.clock_content(moment)
            assert lines_at(moment,upper,lower)[1]=='19:43:00'
            clock=dock.extras.rects()['clock']
            assert clock.width()==clock_width(headers(cfg,'dock_clock_',forms,datetime.now().date()),lower,round(clock.height()),True)
            assert 0<dock.extras.clock.remainingTime()<=1050
            assert dock.grab(clock.toAlignedRect().adjusted(-3,-2,3,2)).save(str(output/'dock-clock-two-lines.png'))
    finally:
        dock.reload();dock.setVisible(was_visible)
    assert dock.extras.width()==original_width
    window=runtime.resources.window
    fmt=cfg['resource_clock_format']
    assert runtime.resources.set_options(resource_clock_format='seconds')
    window.grab()
    layout=plan(window,window.width())
    assert layout['clock']==forms
    clock=layout['positions']['clock']
    assert window.grab().save(str(output/'compact-clock-two-lines.png'))
    height=compact_text_height(cfg,window.height())
    assert clock.width==clock_width(headers(cfg,'resource_clock_',forms,datetime.now().date()),forms[1],height)
    from resource_compact import draw_clock as draw
    for wanted in (16,24,40):
        with patch.dict(cfg,resource_compact_badge_height=wanted):
            window._compact_cache=None;window._compact_surface=None
            with patch('resource_compact.draw_clock',wraps=draw) as rendered:
                frame=window.grab()
            rect=rendered.call_args.args[1]
            side=compact_tile_height(cfg,window.height())
            status=plan(window,window.width())['positions']['device_caps_lock']
            assert status.data[1]==side and rect.height()==min(side+2,window.height()-4)
            assert rect.center().y()==window.height()/2
            assert frame.save(str(output/f'compact-clock-tile-{wanted}.png'))
    assert runtime.resources.set_options(resource_clock_format=fmt)
    checks.append('Dock clock has 6px side insets and the capsule clock 2px. Date and time both use bold text on both surfaces. The centered capsule text has a 2px optical overshoot when it fits, including weekday, lunar date, holidays and ticking seconds.')


def readout_frames(window):
    """Visit each visible resource in each spatial page using its own control."""
    from resource_compact import plan, visible_component_count
    turns, resource_page = window.page_turns, window.component_pages['resources']
    try:
        for page in range(len(plan(window,window.width())['pages'])):
            window.offset = page
            count = visible_component_count(plan(window,window.width()),'resources')
            for index in range(max(1,count)):
                if index:assert window.step_component('resources',1)
                yield page
    finally:
        window.page_turns=turns;window.component_pages['resources']=resource_page;window._compact_cache=None


def check_resource_heights(window,output,checks):
    from PyQt5.QtGui import QFont, QFontInfo, QFontMetricsF, QImage, QPainter
    from compact_text import draw_stacked_text
    from resource_compact import cell_width, draw_clock, paint_compact_body, plan, text
    from resource_options import compact_text_height, compact_tile_height
    cfg=window.service.cfg
    rows=[('traffic','本年流量','370.26 GB',''),('cpu','CPU','68%',''),('memory','内存','56%',''),
          ('gpu','GPU','32%',''),('network','网速','', ''),('cpu_temp','CPU 温度','53.2 °C',''),
          ('cpu_frequency','频率','3201 MHz',''),('board_fan','主板风扇','1300 RPM','')]
    keys=[row[0] for row in rows]
    settings=dict(resource_compact_width=900,resource_compact_auto_width=False,resource_face=False,resource_mail=False,
                  resource_runner_enabled=False,resource_clock=True,resource_clock_format='seconds',resource_compact_pinned=[],
                  resource_compact_rings=True,resource_compact_density='auto')
    original,turns=window.size(),window.page_turns
    try:
        with patch.dict(cfg,settings), patch('resource_compact.compact_values',return_value=rows), \
                patch('resource_compact.compact_badges',return_value=([('focus','04:45')],1)), \
                patch('resource_compact.status_values',return_value=[('battery','电量','62%',(62,'charging'))]), \
                patch.object(window.service,'indicators',None),patch.dict(window.service.latest,network=(460800,8192)):
            for ordered in (False,True):
                cfg.update(resource_compact_order=[*keys,'battery','alert_focus','clock'] if ordered else [],
                           resource_compact_zones={'clock':'right'} if ordered else {})
                for wanted,panel in ((16,35),(20,35),(24,42),(40,52),(40,28)):
                    cfg['resource_compact_badge_height']=wanted
                    window.resize(900,panel);window.offset=0;window._compact_cache=None;window._compact_surface=None
                    frame=window.grab()
                    layout=plan(window,window.width())
                    assert ordered==('positions' in layout)
                    optical=compact_text_height(cfg,panel);tile=compact_tile_height(cfg,panel)
                    # Measure painted glyphs on a transparent row, rather than assuming
                    # font size or the clickable area matches what the user can see.
                    layer=QImage(window.size(),QImage.Format_ARGB32_Premultiplied);layer.fill(Qt.transparent)
                    painter=QPainter(layer)
                    with patch('resource_compact.draw_stacked_text',wraps=draw_stacked_text) as stacks, \
                            patch('resource_compact.text',wraps=text) as inline,patch('resource_compact.draw_clock',wraps=draw_clock) as clock:
                        try:paint_compact_body(window,painter,layout)
                        finally:painter.end()
                    traffic_call=next(call.args for call in stacks.call_args_list if call.args[2][0]=='本年流量')
                    title,font=traffic_call[5]
                    assert (title.pixelSize(),font.pixelSize())==(8 if panel<38 else 9,10 if layout['dense'] else 11)
                    for face in (title,font):
                        assert face.weight()==QFont.Normal and QFontInfo(face).family()==QFontInfo(window.font()).family()
                    assert traffic_call[1].top()==clock.call_args.args[1].top() and traffic_call[1].height()==clock.call_args.args[1].height()
                    for call in inline.call_args_list:
                        if call.args[2].endswith('%') or call.args[2].startswith(('↑ ','↓ ')):
                            assert call.args[4]==font.pixelSize() and not (len(call.args)>5 and call.args[5])
                    traffic_hit=window.compact_bounds[window.compact_shown.index('traffic')].toAlignedRect()
                    ink_rows=[y for y in range(panel) if any(layer.pixelColor(x,y).alpha()>50
                              for x in range(traffic_hit.left(),traffic_hit.right()+1))]
                    assert abs(ink_rows[-1]-ink_rows[0]+1-optical)<=2 and abs(ink_rows[0]+ink_rows[-1]-(panel-1))<=2
                    hits={}
                    for _ in readout_frames(window):
                        window.grab()
                        hits.update(zip(window.compact_shown,window.compact_bounds))
                    assert set(hits)==set(keys),(ordered,wanted,panel,list(hits))
                    assert all(r.height()==optical and r.center().y()==panel/2 for r in hits.values())
                    assert window.status_bounds['battery'].height()==window.reminder_bounds[0].height()==tile
                    assert window.status_bounds['battery'].center().y()==window.reminder_bounds[0].center().y()==panel/2
                    traffic=rows[0]
                    for key,label,value,_ in rows:
                        if key!='network':
                            assert QFontMetricsF(font).horizontalAdvance(value)<=hits[key].width(),(key,value,optical,hits[key])
                    assert cell_width(traffic,layout['dense'],window)==hits['traffic'].width()
                    if ordered and wanted in (20,40) and panel!=28:
                        assert frame.save(str(output/f'compact-resource-readings-{wanted}.png'))
            with patch('resource_compact.compact_badges',return_value=([],0)), patch('resource_compact.status_values',return_value=[]):
                cfg.update(resource_compact_zones={},resource_compact_order=[],resource_compact_badge_height=40)
                window.resize(96,52);window.offset=0;window._compact_cache=None
                narrow=plan(window,96)
                seen=set()
                for _ in readout_frames(window):
                    window.grab()
                    current=plan(window,96)
                    if current['clock']:assert 20<=current['clock_width']<=80
                    seen.update(current['positions'])
                assert {'resources','clock','traffic'}<=seen
                assert cell_width(('cpu','CPU','9%',''),True,window)==cell_width(('cpu','CPU','100%',''),True,window)
    finally:
        window.resize(original);window.page_turns=turns;window._compact_cache=None;window._compact_surface=None;window.grab()
    checks.append('Resource titles and values keep the original widget font, regular weight and 8/9px and 10/11px sizes. Both text lines share the clock band across tile heights, densities and saved layouts; network and inline percentages remain regular.')


def check_paging(window, app, checks):
    from PyQt5.QtCore import QPoint, QPointF
    from PyQt5.QtGui import QWheelEvent
    from resource_compact import clock_rows, plan

    service = window.service
    cfg = service.cfg
    readings = [(key,key,'35%','') for key in ('cpu','memory','network','gpu')]
    cities = [dict(name='天津',temperature=10,code=0),dict(name='北京',temperature=14,code=0)]
    settings = dict(resource_clock=True,resource_clock_format='seconds',resource_clock_festival=False,
                    resource_clock_weekday=True,resource_clock_lunar=False,
                    resource_compact_rotate_left=True,resource_compact_rotate_center=True,resource_compact_rotate_right=True,
                    resource_face=True,resource_runner_enabled=False,resource_mail=False,resource_traffic=False,
                    resource_system_status=False,resource_music=False,resource_weather=True,resource_weather_compact=True,
                    resource_compact_metrics=['cpu','memory','network','gpu'],resource_compact_zones={'clock':'center','face':'right'})
    def wheel(delta):
        pos=QPointF(1,16)
        event=QWheelEvent(pos,QPointF(window.mapToGlobal(pos.toPoint())),QPoint(),QPoint(0,delta),
                          Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False)
        app.sendEvent(window,event)
        assert event.isAccepted()
    try:
        with patch.dict(cfg,settings), patch.object(window,'values',readings), \
                patch.object(service,'reminders',return_value=()), patch.object(service,'indicators',None), \
                patch.object(service,'extras',SimpleNamespace(weather=cities)):
            window.offset=0;window._compact_cache=None;window.resize(200,35);window.sync_animation()
            first=plan(window,200)
            assert list(first['zone_widths'])==['left','center','right'] and window.rotate.isActive()
            stationary={key:first['positions'][key] for key in ('clock','face')}
            seen=set();temperatures=set()
            for i in range(len(first['pages'])):
                slots=plan(window,200)['positions']
                assert all(slots[key]==item for key,item in stationary.items())
                assert all(a.x+a.width+3<=b.x for a,b in zip(slots.values(),list(slots.values())[1:]))
                seen.update(slots)
                if 'weather' in slots:temperatures.add(slots['weather'].data[2])
                wheel(-120)
            assert seen=={'clock','face','resources','weather'} and temperatures=={'10℃','14℃'}
            # Left and right each have two readings and the center has two date lines.
            cfg.update(resource_compact_zones={'traffic':'right','clock':'center','face':'right'},resource_clock_format='date_seconds',
                       resource_compact_rotate_interval=11,resource_compact_rotate_center=False,resource_traffic=True)
            cfg['resource_compact_metrics']=[*cfg['resource_compact_metrics'],'traffic']
            window.offset=0;window._compact_cache=None;window.resize(560,35);window.sync_rotation()
            assert window.rotate.isActive() and window.rotate.interval()==11000
            def visible():
                layout=plan(window,window.width());items=layout['positions']
                return items['weather'].data[2],clock_rows(window,layout['clock'])[0],items['traffic'].data[1]
            with patch.object(window,'underMouse',return_value=False):
                before=visible();window.next_page();after=visible()
                assert before[0]!=after[0] and before[1]==after[1] and before[2]!=after[2]
                cfg.update(resource_compact_rotate_left=False,resource_compact_rotate_center=True,resource_compact_rotate_right=False)
                window.sync_rotation();window.next_page()
                again=visible()
                assert after[0]==again[0] and after[1]!=again[1] and after[2]==again[2]
                cfg['resource_compact_rotate_center']=False;window.sync_rotation()
                assert not window.rotate.isActive()
                window.next_page();assert visible()==again
                wheel(-120);assert all(old!=new for old,new in zip(again,visible()))
            # Extremely narrow rows may share the physical space; manual paging still reaches every value.
            window.resize(96,35);window.offset=0;window._compact_cache=None
            narrow=plan(window,96);assert len(narrow['bands'])>1
            cfg['resource_compact_rotate_right']=True;window.sync_rotation()
            visible_keys=set();temps=set();dates=set()
            for _ in range(len(narrow['pages'])):
                page=plan(window,96);slots=page['positions']
                visible_keys.update(slots)
                if 'weather' in slots:temps.add(slots['weather'].data[2])
                if page['clock']:dates.add(clock_rows(window,page['clock'])[0])
                wheel(-120)
            assert set(seen)|{'traffic'}==visible_keys and len(temps)==len(dates)==2
            with patch.dict(cfg,resource_compact_order=[],resource_compact_zones={},resource_compact_pinned=['weather'],
                            resource_compact_rotate_left=False,resource_compact_rotate_right=True):
                window.offset=0;window._compact_cache=None;window.resize(560,35);window.sync_rotation()
                old=plan(window,560);assert 'positions' not in old and old['pinned'][0][0]=='weather'
                date=clock_rows(window,old['clock'])[0]
                with patch.object(window,'underMouse',return_value=False):window.next_page()
                current=plan(window,560)
                assert current['pinned']==old['pinned'] and clock_rows(window,current['clock'])[0]!=date
                wheel(-120);assert plan(window,560)['pinned']!=old['pinned']
            cfg.update(resource_compact_rotate_left=True,resource_compact_rotate_center=True,resource_traffic=False,
                       resource_clock_format='seconds')
            # With one city and enough room, neither a sample nor the clock's seconds trigger a turn.
            cities.pop();window._compact_cache=None;window.resize(560,35);window.sync_animation()
            assert len(plan(window,560)['pages'])==1 and not window.rotate.isActive() and window.clock_tick.isActive()
            # A second date line alone is pageable, without moving the time or the other items.
            cfg.update(resource_clock_format='date_seconds',motion_enabled=True)
            window.offset=0;window._compact_cache=None;window.sync_animation()
            assert len(plan(window,560)['pages'])==2 and window.rotate.isActive()
            forms=plan(window,560)['clock']
            date=clock_rows(window,forms)[0]
            with patch.object(window,'underMouse',return_value=True):
                window.rotate.timeout.emit()
            assert window.offset==0
            with patch.object(window,'underMouse',return_value=False):
                window.rotate.timeout.emit()
            assert window.offset==1 and not window.compact_scroll and clock_rows(window,forms)[0]!=date
            cfg['resource_compact_rotate_center']=False;window.sync_animation()
            assert not window.rotate.isActive() and window.clock_tick.isActive()
            with patch.object(window,'underMouse',return_value=False):
                window.rotate.timeout.emit()
            assert window.offset==1
            wheel(120);assert window.offset==0 and clock_rows(window,forms)[0]==date
            cfg['resource_compact_rotate_center']=True;window.sync_rotation()
            assert window.rotate.isActive()
            cfg['resource_fold']='ball';window.sync_rotation()
            assert not window.rotate.isActive()
    finally:
        window.offset=0;window._compact_cache=None;window.sync_window()
    checks.append('Only zones with extra content rotate. Single-page, ball and disabled rotation are idle. City and calendar pages remain wheel-accessible, hover pauses rotation, and ticking seconds keep their position.')
    checks.append('Independent left, center and right page positions survive timer changes and manual wheel turns. An 11-second interval, disabled zones and narrow shared pages were checked on the real capsule.')


def check_weather_resize(window, app, output, checks):
    from PyQt5.QtCore import QRectF
    from capsule_badge_resize_tests import drag_frames
    from resource_compact import chip, content_badge_rect, plan, stacked_badge_width
    from resource_weather_style import paint_weather_icon

    cfg = window.service.cfg
    first, turns = window.geometry(), window.page_turns
    readings = [('weather','武清区','4℃',dict(temperature=4,code=2)), ('traffic','本年流量','370.95 GB','')]
    settings = dict(resource_fold='pill',resource_compact_width=400,resource_compact_height=42,
                    resource_compact_badge_height=20,resource_compact_auto_width=False,resource_compact_density='auto',
                    resource_face=False,resource_runner_enabled=False,resource_mail=False,resource_clock=True,resource_clock_format='seconds',
                    resource_compact_pinned=['weather'],resource_compact_rotate_left=False,resource_compact_rotate_center=False,resource_compact_rotate_right=False)
    try:
        with patch.dict(cfg,settings), patch('resource_compact.compact_values',return_value=readings), \
                patch('resource_compact.compact_badges',return_value=([],0)), patch('resource_compact.status_values',return_value=[]), \
                patch.object(window.service,'indicators',None),patch.object(window.service,'set_options',return_value=True):
            for ordered,edge in ((False,'r'),(True,'l'),(True,'rb')):
                cfg['resource_compact_order']=['weather','traffic','clock'] if ordered else []
                cfg['resource_compact_zones']={'weather':'center','clock':'right'} if ordered else {}
                window.offset=0
                sizes=[]
                frames=[(w,37 if edge=='rb' and i%2 else 42) for i,w in enumerate((400,419,420,464,488,412,400))]
                for wide,_ in drag_frames(window,app,edge,frames):
                    with patch('resource_weather_style.paint_weather_icon',wraps=paint_weather_icon) as icon, \
                            patch('resource_compact.chip',wraps=chip) as background:
                        frame=window.grab()
                    mark=icon.call_args.args[1]
                    hit=window.compact_bounds[window.compact_shown.index('weather')]
                    sizes.append((hit.width(),hit.height(),mark.width(),mark.height()))
                    assert mark.width()==mark.height() and hit.contains(mark) and hit==background.call_args.args[1]
                    if ordered and edge=='l' and wide in (400,488):
                        assert frame.save(str(output/f'weather-resize-{wide}.png'))
                window.grab()
                assert len(set(sizes))==1,(ordered,edge,sizes)
                assert window.compact_bounds[window.compact_shown.index('weather')].width()==sizes[0][0]
                assert ('positions' in plan(window,window.width()))==ordered

            readings.append(('weather','巴音郭楞蒙古自治州','−18℃',dict(temperature=-18,code=71)))
            window.resize(488,42)
            for zone in ('left','center','right'):
                cfg['resource_compact_zones']={'weather':zone,'clock':'right'}
                for page,(_,place,temp,_) in enumerate((readings[0],readings[-1])):
                    window.offset=page;window._compact_cache=None;window.grab()
                    hit=window.compact_bounds[window.compact_shown.index('weather')]
                    slot=plan(window,488)['positions']['weather']
                    assert slot.data[1:3]==(place,temp) and hit.width()==stacked_badge_width(place,temp)
                    spare=slot.width-hit.width()
                    offset=spare if zone=='right' else spare/2 if zone=='center' else 0
                    assert hit.left()==slot.x+offset
                    if zone=='center':
                        assert hit.center().x()==window.width()/2
                    elif page==0:
                        assert spare>0
            cfg['resource_compact_zones']={'weather':'center'}
            narrow=content_badge_rect(QRectF(0,0,28,20),readings[0],cfg)
            assert narrow==QRectF(4,0,20,20)
    finally:
        window.setGeometry(first);window.page_turns=turns;window._compact_cache=None;window._compact_surface=None
        window.grab()
    checks.append('The same weather badge and square icon retain their painted and clickable dimensions before, during and after left, right and corner drags across compact layout breakpoints.')


def run(api,runtime,app,output,checks):
    from capsule_order import NAMES,configured_items,display_order
    from capsule_order_layout import ball_slots
    from config_transfer import normalize
    from resource_compact import plan
    from resource_options import COMPACT_ITEMS,DEFAULTS,DEVICE_ALERTS,METRICS
    from resource_runner import capsule_rect
    from resource_settings import ResourceOptions
    cfg=runtime.dock.cfg
    service=runtime.resources
    before=copy.deepcopy(cfg)
    auto=service.auto_compact
    options=None
    try:
        all_on=dict(cfg,resource_component_locations={},resource_compact_metrics=list(COMPACT_ITEMS))
        all_on.update({key:True for key in all_on if key.startswith(('resource_alert_','resource_compact_')) and type(all_on[key]) is bool})
        all_on.update({'resource_'+key:True for key in METRICS})
        all_on.update(resource_alert_stopwatch=True,resource_alert_alarm=True,resource_ai=True,resource_pomodoro=True,
                      resource_water_enabled=True,resource_agenda=True,resource_weather=True,resource_weather_compact=True,
                      resource_music=True,resource_mail=True,resource_mail_icon=True,resource_mail_notifications=True,
                      resource_runner_enabled=True,resource_face=True,resource_clock=True,resource_quota_alert=True)
        assert set(configured_items(all_on))==set(NAMES),set(NAMES)-set(configured_items(all_on))
        all_on['resource_component_locations']={'resources':'desktop','weather':'desktop','ai':'desktop','traffic':'desktop'}
        assert not {'resources','ai','weather','traffic','bluetooth'}.intersection(configured_items(all_on))
        cfg.update(copy.deepcopy(DEFAULTS))
        cfg.update(resource_enabled=True,resource_collapsed=True,resource_fold='pill',resource_auto_hide=False,
                   resource_compact_width=560,resource_compact_auto_width=False,resource_edge='free',
                   resource_compact_metrics=['memory','board_temp','volume'],resource_compact_pinned=['memory','cpu'],
                   resource_compact_order=['memory','cpu'],resource_system_status=True,resource_board_temp=False,
                   resource_ai=False,resource_ai_tray=False,resource_music=False,resource_weather=False,
                   resource_face=True,resource_runner_enabled=True,resource_mail=True,resource_mail_icon=True,
                   resource_mail_notifications=False,resource_alert_mail_code=False,resource_alert_almanac=False,
                   resource_pomodoro=False,resource_agenda=False,resource_mail_accounts=[],
                   resource_component_locations={},resource_hide_unavailable=True,motion_enabled=False)
        cfg.update({'resource_alert_'+key:key in ('caps_lock','volume') for key in DEVICE_ALERTS})
        service.auto_compact=None;service.sync()
        window=service.window
        options=ResourceOptions(service);options.tabs.setCurrentIndex(2);options.show();app.processEvents()
        initial=list(configured_items(cfg))
        assert set(initial)=={'face','resources','volume','mail','runner','device_caps_lock','clock'} and initial[-1]=='clock'
        sort_dialog(options,initial)
        # Unsaved changes on a released lazy page and directly on this page both count.
        options.tabs.setCurrentIndex(5);options.fields['resource_board_temp'].setChecked(True)
        options.tabs.setCurrentIndex(2);options.compact_fields['cpu'].setChecked(True)
        options.compact_fields['memory'].setChecked(False)
        draft=initial
        target=['device_caps_lock','clock','volume','resources','runner','mail','face']
        sort_dialog(options,draft,target,split=(2,5),accept=False)
        assert 'resource_compact_order' not in options.orders and list(configured_items(cfg))==initial
        sort_dialog(options,draft,target,split=(2,5),shot=output/'compact-order-settings.png')
        assert list(configured_items(cfg))==initial
        sort_dialog(options,target)
        assert 'resource_compact_rotate' not in options.fields
        options.fields['resource_compact_rotate_interval'].setValue(11)
        options.fields['resource_compact_rotate_center'].setChecked(False)
        options.tabs.setCurrentIndex(5);options.tabs.setCurrentIndex(2)
        assert options.fields['resource_compact_rotate_interval'].value()==11 and not options.fields['resource_compact_rotate_center'].isChecked()
        app.processEvents()
        scroll=options.tabs.widget(2).layout().itemAt(0).widget()
        section=options.fields['resource_compact_auto_width'].parentWidget()
        scroll.verticalScrollBar().setValue(section.mapTo(scroll.widget(),section.rect().topLeft()).y()-5)
        zone_field=options.fields['resource_compact_rotate_center']
        scroll.ensureWidgetVisible(zone_field,0,12)
        assert scroll.viewport().rect().contains(zone_field.mapTo(scroll.viewport(),zone_field.rect().center()))
        app.processEvents();assert options.grab().save(str(output/'compact-pagination-settings.png'))
        assert options.fields['resource_compact_rotate_interval'].isEnabled() and options.fields['resource_compact_rotate_left'].isEnabled()
        assert options.commit()
        options.close();options.deleteLater();options=None
        stored=api.load_config()
        assert list(configured_items(stored))==target and len(stored['resource_compact_order'])==len(NAMES)
        assert 'resource_compact_rotate' not in stored
        assert stored['resource_compact_rotate_interval']==11 and not stored['resource_compact_rotate_center']
        legacy={k:v for k,v in stored.items() if not k.startswith('resource_compact_rotate_')}
        legacy['resource_compact_rotate']=False
        imported=normalize(legacy,api)
        assert 'resource_compact_rotate' not in imported and imported['resource_compact_rotate_interval']==6
        assert not any(imported['resource_compact_rotate_'+zone] for zone in ('left','center','right'))
        migrated=normalize(dict(stored,resource_compact_order=['face','cpu','clock','memory','traffic'],
                                resource_compact_zones={'cpu':'left','memory':'center','clock':'right'},
                                resource_compact_metrics=['memory','traffic'],resource_memory=True),api)
        assert migrated['resource_compact_order']==['face','clock','resources','traffic']
        assert migrated['resource_compact_zones']=={'resources':'center','clock':'right'}
        assert configured_items(normalize(stored,api))==configured_items(stored)
        assert normalize(stored,api)['resource_compact_zones']==stored['resource_compact_zones']
        assert 'resources' in configured_items(cfg) and not {'cpu','board_temp','memory'}.intersection(configured_items(cfg))
        # Disabled items keep their own positions through edits and re-enabling.
        options=ResourceOptions(service);options.tabs.setCurrentIndex(2);options.show();app.processEvents()
        options.fields['resource_runner_enabled'].setChecked(False)
        reduced=[k for k in target if k!='runner'];swapped=[reduced[1],reduced[0],*reduced[2:]]
        sort_dialog(options,reduced,swapped)
        options.fields['resource_runner_enabled'].setChecked(True)
        restored=['clock','device_caps_lock',*target[2:]]
        sort_dialog(options,restored)
        options.reject();options.deleteLater();options=None
        assert list(configured_items(cfg))==target
        indicators=service.indicators
        indicators.observe('caps_lock',True);indicators.observe('volume',(42,False))
        service.accept_sample(dict(cpu=31,volume=(42,False),time=time.monotonic()))
        expected=target
        for shape in ('pill','bar'):
            assert service.set_options(resource_fold=shape)
            window.offset=0;image=window.grab();layout=plan(window,window.width())
            slots=layout['positions']
            assert list(slots)==expected,(list(slots),expected)
            assert all(a.x+a.width<=b.x for a,b in zip(slots.values(),list(slots.values())[1:]))
            assert slots['device_caps_lock'].x==8 and slots['face'].x+slots['face'].width==window.width()-8
            assert abs(slots['volume'].x+slots['runner'].x+slots['runner'].width-window.width())<=1
            assert slots['clock'].x < slots['resources'].x and slots['volume'].slot.kind=='device'
            assert window.status_bounds['mail'].center().x()>capsule_rect(window).right()
            assert window.compact_bounds[window.compact_shown.index('cpu')].left()==slots['resources'].x
            assert image.save(str(output/('compact-order-'+shape+'.png')))
        check_clocks(api,runtime,app,output,checks)
        check_resource_heights(window,output,checks)
        check_weather_resize(window,app,output,checks)
        from capsule_badge_resize_tests import check_centering, check_other_badges
        check_other_badges(window,app,output,checks)
        check_centering(window,app,output,checks)
        with patch.object(service,'open_component') as opened:
            window.expand_from(window.status_bounds['mail'].center().toPoint())
            opened.assert_called_once_with('mail')
        assert service.compact
        # Rain, per-city weather readings, the music card, running timers, a
        # pending agenda and a low-battery reminder all use the same spatial order.
        weather=[dict(name='示例城市',temperature=10,code=61),dict(name='另一城市',temperature=13,code=0)]
        fake_deck=SimpleNamespace(providers=[],media={'track':{'title':'示例曲目','state':'Paused'}},alert_until=0.)
        named=['music','alert_weather','weather','alert_alarm','device_caps_lock','alert_stopwatch','resources',
               'alert_quota','alert_mail_new','alert_mail_code','alert_agenda','alert_battery','alert_focus','alert_water','alert_almanac','clock']
        alerts=(('weather_notice','雨'),('alarm','17:30'),('stopwatch','01:23'),('quota_notice','低额度'),
                ('mail_new','新邮件'),('mail_code','123456'),('agenda','会议'),('battery','10%'),
                ('focus','12:34'),('water','喝水'),('almanac','节气'))
        with patch.dict(cfg,resource_music=True,resource_weather=True,resource_compact_zones={},resource_compact_order=[*named,*(k for k in NAMES if k not in named)],
                        resource_alert_almanac=True,resource_compact_auto_width=False), \
                patch.object(service,'extras',SimpleNamespace(weather=weather)),patch.object(service,'deck',fake_deck), \
                patch.object(service,'reminders',return_value=alerts):
            window.resize(1360,35);window._compact_cache=None;window.offset=0
            first=plan(window,window.width())['positions']
            assert [key for key in first if key in named]==named
            window.grab()
            assert window.compact_media and set(window.reminder_kinds)=={kind for kind,_ in alerts}
            assert first['weather'].data[2]=='10℃'
            window.offset=1;assert plan(window,window.width())['positions']['weather'].data[2]=='13℃'
        window.offset=0
        assert service.set_options(resource_compact_width=96)
        count=len(plan(window,window.width())['pages']);seen=set()
        assert 1<count<100
        for page in range(count):
            window.offset=page;window.grab()
            slots=plan(window,window.width())['positions']
            assert list(slots)==[key for key in expected if key in slots]
            assert all(0<=s.x<s.x+s.width<=window.width() for s in slots.values())
            seen.update(slots)
        assert seen==set(expected),(seen,expected)
        check_paging(window,app,checks)
        from calendar_almanac_tests import check_badge_rotation
        check_badge_rotation(window,output,checks)
        assert service.set_options(resource_fold='ball',resource_compact_width=560)
        window.grab()
        ball=ball_slots(window,window.width())
        assert list(ball)==['device_caps_lock','volume','runner','mail','face'],list(ball)
        middle=[ball[key] for key in ball if cfg['resource_compact_zones'].get(key)=='center']
        assert middle and middle[0].x+middle[-1].x+middle[-1].width==window.width()
        assert all(a.x+a.width<=b.x for a,b in zip(ball.values(),list(ball.values())[1:]))
        assert capsule_rect(window).right()<window.status_bounds['mail'].left()
        assert window.grab().save(str(output/'compact-order-ball.png'))
        with patch.dict(cfg,resource_face=False,resource_clock=False,resource_runner_enabled=False,
                        resource_mail_icon=False,resource_compact_metrics=[],
                        resource_alert_caps_lock=False,resource_alert_volume=False):
            assert not configured_items(cfg)
            options=ResourceOptions(service);options.tabs.setCurrentIndex(2);options.show();app.processEvents()
            sort_dialog(options,[])
        checks.append('Compact order filters live checkbox drafts and feature placement, preserves disabled positions, cancellation and config imports, and places the clock, readings, device icons, mail, face and pet in the chosen order across pills, bars, balls and narrow pages.')
        checks.append('Left, center and right assignments persist with their own ordering. On wide pills and bars the middle block is centered and both outer blocks hug their edges; 96px overflow pages have no collisions.')
    finally:
        if options:options.close();options.deleteLater()
        cfg.clear();cfg.update(before);service.auto_compact=auto
        api.save_config(cfg);service.sync();app.processEvents()
