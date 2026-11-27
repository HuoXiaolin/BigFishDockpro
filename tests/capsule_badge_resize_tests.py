"""Check the painted faces and hit regions while the real resize handles are held."""
from types import SimpleNamespace
from unittest.mock import patch

from PyQt5.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PyQt5.QtGui import QMouseEvent


def drag_frames(window, app, edge, sizes):
    start_width,start_height=sizes[0]
    bounds=QRect(0,0,start_width,start_height)
    bounds.moveCenter(app.primaryScreen().availableGeometry().center())
    window.setGeometry(bounds)
    window._compact_cache=window._compact_surface=None
    window.resize_edges.sync()
    handle=window.resize_edges.handles[edge]
    origin=handle.mapToGlobal(handle.rect().center())

    def mouse(kind, point):
        local=QPointF(handle.mapFromGlobal(point))
        buttons=Qt.NoButton if kind==QEvent.MouseButtonRelease else Qt.LeftButton
        trigger=Qt.NoButton if kind==QEvent.MouseMove else Qt.LeftButton
        app.sendEvent(handle,QMouseEvent(kind,local,QPointF(point),trigger,buttons,Qt.NoModifier))

    point=origin
    mouse(QEvent.MouseButtonPress,origin)
    try:
        for width,height in sizes:
            dx,dy=width-start_width,height-start_height
            point=origin+QPoint(-dx if 'l' in edge else dx,-dy if 't' in edge else dy)
            mouse(QEvent.MouseMove,point)
            assert (window.width(),window.height())==(width,height) and handle.active
            window._compact_surface=None
            yield width,height
    finally:
        mouse(QEvent.MouseButtonRelease,point)
        assert not handle.active


def check_centering(window, app, output, checks):
    from resource_compact import natural_width, plan

    service=window.service
    cfg=service.cfg
    original,turns=window.geometry(),window.page_turns
    cities=[('weather','武清区','4℃',{'temperature':4,'code':2}),
            ('weather','巴音郭楞蒙古自治州','−18℃',{'temperature':-18,'code':71})]
    quota=('ai','Codex','59%',dict(provider={'id':'Codex'},reading=SimpleNamespace(remaining=59,stale=False,daily=None)))
    rows=[quota,*cities,('traffic','本年流量','370.95 GB',''),('music','音乐','风',{'state':'Paused'})]
    left=['face','ai','weather','traffic','music','mail','alert_quota']
    right=['clock','battery']
    settings=dict(resource_compact_order=[*left,'agenda',*right],resource_face=True,resource_runner_enabled=False,
                  resource_mail=True,resource_mail_icon=True,resource_clock=True,resource_clock_format='seconds',
                  resource_compact_density='auto',resource_compact_auto_width=False,resource_music_text='title',
                  resource_clock_festival=False,resource_clock_lunar=False,resource_clock_weekday=True,
                  resource_compact_badge_height=20,resource_compact_rotate_left=False,resource_compact_rotate_center=False,resource_compact_rotate_right=False)
    agenda=('agenda','下一项日程 · 项目周会')
    try:
        with patch.dict(cfg,settings),patch('resource_compact.compact_values',return_value=rows), \
                patch('resource_compact.status_values',return_value=[('battery','电量','68%',(68,'battery'))]), \
                patch('resource_compact.compact_badges',return_value=([('quota_notice','额度提醒'),agenda],1)), \
                patch.object(service,'indicators',None),patch.object(service,'set_options',return_value=True):
            for mirrored,shape in ((False,'pill'),(True,'bar')):
                cfg.update(resource_fold=shape,resource_compact_zones={
                    **dict.fromkeys(left,'right' if mirrored else 'left'),
                    **dict.fromkeys(right,'left' if mirrored else 'right'),'agenda':'center'})
                for width,_ in drag_frames(window,app,'r',[(w,35) for w in (455,420,419,400,488,455)]):
                    window.offset=0
                    layout=plan(window,width)
                    seen=set()
                    for page in range(len(layout['pages'])):
                        window.offset=page;frame=window.grab()
                        items=plan(window,width)['positions']
                        hit=window.reminder_bounds[window.reminder_kinds.index('agenda')]
                        assert hit.center().x()==width/2,(shape,width,page,hit,items['agenda'])
                        assert all(a.x+a.width+3<=b.x for a,b in zip(items.values(),list(items.values())[1:]))
                        seen.update(items)
                        if width==455 and not page and not mirrored:
                            assert frame.save(str(output/'compact-agenda-centered.png'))
                    assert seen==set(cfg['resource_compact_order'])
            cfg['resource_compact_auto_width']=True
            cfg['resource_compact_zones'].update(agenda='center',weather='center')
            width=natural_width(window,1200)
            window.resize(width,35);window._compact_cache=None
            for page in range(2):
                window.offset=page;window.grab()
                items=plan(window,width)['positions']
                assert set(items)==set(cfg['resource_compact_order'])
                weather=window.compact_bounds[window.compact_shown.index('weather')]
                event=window.reminder_bounds[window.reminder_kinds.index('agenda')]
                start,end=min(weather.left(),event.left()),max(weather.right(),event.right())
                assert start+end==width and abs(weather.right()+3-event.left())<.001,(page,width,weather,event)
            window.resize(96,35);window._compact_cache=None
            layout=plan(window,96);seen=set()
            for page in range(len(layout['pages'])):
                window.offset=page;window.grab();items=plan(window,96)['positions']
                middle=[p for key,p in items.items() if cfg['resource_compact_zones'][key]=='center']
                if middle:assert middle[0].x+middle[-1].x+middle[-1].width==96
                assert all(a.x+a.width+3<=b.x for a,b in zip(items.values(),list(items.values())[1:]))
                seen.update(items)
            assert seen==set(cfg['resource_compact_order'])
    finally:
        window.setGeometry(original);window.page_turns=turns;window._compact_cache=window._compact_surface=None;window.grab()
    checks.append('The middle group stays at the exact geometric center of the full capsule with asymmetric wings, resizing and paging. Variable city labels and agenda center together; automatic width and 96px overflow preserve all items.')


def check_other_badges(window, app, output, checks):
    from PyQt5.QtGui import QImage, QPainter
    from capsule_indicators import draw_symbol
    from resource_compact import cell_width, chip, paint_badges, paint_values, plan
    from resource_pomodoro_view import reminder_icon
    from resource_provider_icons import paint_provider_mark

    service=window.service
    cfg=service.cfg
    original,turns=window.geometry(),window.page_turns
    settings=dict(resource_compact_height=42,resource_compact_badge_height=20,resource_compact_width=400,
                  resource_compact_auto_width=False,resource_compact_density='auto',resource_compact_rotate_left=False,resource_compact_rotate_center=False,resource_compact_rotate_right=False,
                  resource_runner_enabled=False,resource_face=True,resource_face_scale=100,resource_mail=False,
                  resource_clock=False,resource_fold='pill')
    timepoints=(400,419,420,488,412,400)
    quota=('ai','Codex','59%',dict(provider={'id':'Codex'},reading=SimpleNamespace(remaining=59,stale=False,daily=None)))
    balance=('ai','网关','¥12,345.67',dict(provider={'id':'gateway'},reading=None))
    rows=[quota,balance]
    statuses=[('battery','电量','68%',(68,'battery')),('bluetooth','外设电量','',[]),('connection','网络','Wi-Fi','Wi-Fi'),
              ('volume','音量','58%',(58,False)),('brightness','亮度','75%',75)]
    try:
        with patch.dict(cfg,settings),patch.object(service,'set_options',return_value=True), \
                patch('resource_compact.compact_values',return_value=rows), \
                patch('resource_compact.compact_badges',return_value=([],0)),patch('resource_compact.status_values',return_value=[]), \
                patch.object(service,'indicators',None):
            for ordered,edge in ((False,'r'),(True,'l')):
                cfg.update(resource_compact_order=['face','ai','music'] if ordered else [],
                           resource_compact_zones={'ai':'center','music':'right'} if ordered else {},
                           resource_compact_pinned=['ai','music'])
                for mode,song in (('wave',''),('title','风'),('lyrics','远方的海浪轻轻拍打岸边')):
                    cfg['resource_music_text']=mode
                    rows[:]=[quota,balance,('music','音乐',song,{'state':'Paused'})]
                    window.offset=0
                    recorded=[]
                    for width,height in drag_frames(window,app,edge,[(w,42) for w in timepoints]):
                        with patch('resource_compact.chip',wraps=chip) as paints, \
                                patch('resource_provider_icons.paint_provider_mark',wraps=paint_provider_mark) as mark:
                            frame=window.grab()
                        hits=dict(zip(window.compact_shown,window.compact_bounds))
                        painted=[call.args[1] for call in paints.call_args_list]
                        assert all(hits[key] in painted for key in ('ai','music'))
                        assert mark.call_args.args[1].width()==mark.call_args.args[1].height()
                        layout=plan(window,width)
                        recorded.append((hits['ai'].width(),hits['music'].width(),layout['face']))
                        if mode=='title' and ordered and width in (400,488):
                            assert frame.save(str(output/f'compact-other-badges-{width}.png'))
                    assert len(set(recorded))==1,(edge,mode,recorded)
                    for page,provider in enumerate((quota,balance)):
                        window.offset=page;window._compact_cache=None;window.grab()
                        hits=dict(zip(window.compact_shown,window.compact_bounds))
                        assert hits['ai'].width()==cell_width(provider,True,window),(provider[2],hits['ai'])
                        if provider[3]['reading']:
                            assert window.compact_ai_hits[0][0]==hits['ai']
                        else:
                            assert not window.compact_ai_hits
            # If the label cannot fit, the painted tile and the hit area must both
            # reduce to a square, even when the configured tile is taller than its slot.
            with patch.dict(cfg,resource_compact_badge_height=40):
                window.resize(400,48)
                image=QImage(window.size(),QImage.Format_ARGB32_Premultiplied);image.fill(Qt.transparent)
                painter=QPainter(image)
                try:
                    for row in (balance,rows[-1],('weather','武清区','4℃',{'temperature':4,'code':2})):
                        with patch('resource_compact.chip',wraps=chip) as draw:
                            hits=paint_values(window,painter,[row],0,24,28,True,[28])
                        assert len(hits)==1 and hits[0]==draw.call_args.args[1]
                        assert (hits[0].width(),hits[0].height(),hits[0].center().y())==(28,28,24)
                    with patch('resource_compact.chip',wraps=chip) as draw:
                        paint_badges(window,painter,[('agenda','项目周会',28,45)],28,24)
                    hit=window.reminder_bounds[-1]
                    assert hit==draw.call_args.args[1] and (hit.width(),hit.height(),hit.center().y())==(28,28,24)
                finally:
                    painter.end()
            rows.clear()
            cfg.update(resource_face=False,resource_compact_pinned=[],resource_compact_order=[],resource_compact_zones={})
            reminders=[('agenda','项目周会与设备联调工作安排 · 11/27'),('focus','25:00'),('water','200 mL'),
                       ('stopwatch','01:23'),('alarm','18:30'),('battery','12%'),('mail_code','123456'),
                       ('mail_new','新邮件'),('quota_notice','额度提醒'),('weather_notice','大风'),('almanac','小雪')]
            for shape,ordered in (('pill',False),('bar',True)):
                cfg.update(resource_fold=shape,resource_compact_order=['clock'] if ordered else [])
                for start in range(0,len(reminders),3):
                    batch=reminders[start:start+3]
                    with patch('resource_compact.compact_badges',return_value=(batch,len(batch))):
                        previous=None
                        for width,height in drag_frames(window,app,'rb',[(w,42-i%2*5) for i,w in enumerate(timepoints)]):
                            with patch('resource_compact.chip',wraps=chip) as paints, \
                                    patch('resource_pomodoro_view.reminder_icon',wraps=reminder_icon) as icons:
                                window.grab()
                            bounds=dict(zip(window.reminder_kinds,window.reminder_bounds))
                            assert set(bounds)=={kind for kind,_ in batch}
                            assert list(bounds.values())==[call.args[1] for call in paints.call_args_list]
                            assert all(rect.width()==rect.height() and bounds[kind].contains(rect)
                                       for _,rect,kind,_ in (call.args for call in icons.call_args_list))
                            sizes={key:rect.size() for key,rect in bounds.items()}
                            assert previous is None or previous==sizes,(shape,width,previous,sizes)
                            previous=sizes
            cfg.update(resource_fold='pill',resource_compact_order=['mail','face','runner'],resource_mail=True,
                       resource_mail_icon=True,resource_runner_enabled=True,resource_face=True)
            with patch('resource_compact.status_values',return_value=statuses):
                previous=None
                for width,height in drag_frames(window,app,'r',[(w,42) for w in timepoints]):
                    window.grab()
                    layout=plan(window,width)
                    fixed={key:layout['positions'][key].width for key in ('runner','mail','face')}
                    fixed.update({key:rect.width() for key,rect in window.status_bounds.items()})
                    assert {row[0] for row in statuses}<=fixed.keys()
                    assert previous is None or previous==fixed,(width,previous,fixed)
                    previous=fixed

        states=dict(caps_lock=False,input_mode='zh',num_lock=True,microphone=True,touchpad=True,
                    bluetooth_link=(('one','耳机'),),network_link=(('lan','办公网'),),volume=(58,False),brightness=75)
        indicators=service.indicators
        clock=[100.]
        with patch.dict(cfg,{**settings,'resource_face':False,'motion_enabled':True}),patch.object(service,'set_options',return_value=True), \
                patch('resource_compact.compact_values',return_value=[]),patch('resource_compact.compact_badges',return_value=([],0)), \
                patch('resource_compact.status_values',return_value=[]),patch.object(indicators,'selected',tuple(states)), \
                patch.object(indicators,'values',states),patch.object(indicators,'clock',side_effect=lambda:clock[0]), \
                patch.object(indicators,'transitions',{'volume':(100.,0.,'系统音量 58%'),'bluetooth_link':(100.,0.,'已连接 耳机')}):
            for ordered in (False,True):
                cfg.update(resource_compact_order=['clock'] if ordered else [],resource_compact_zones={})
                for now in (100.,101.,105.1):
                    clock[0]=now
                    previous=None
                    for width,height in drag_frames(window,app,'l',[(w,42) for w in timepoints]):
                        with patch.object(indicators,'paint',wraps=indicators.paint) as paints, \
                                patch('capsule_indicators.draw_symbol',wraps=draw_symbol) as symbols:
                            window.grab()
                        tiles={kind:(side,size) for call in paints.call_args_list for kind,side,size,_ in call.args[1]}
                        assert tiles.keys()==states.keys()
                        assert all(call.args[1].width()==call.args[1].height()==20 for call in symbols.call_args_list)
                        expanded={key for key,(side,size) in tiles.items() if size>side}
                        assert expanded==({'volume','bluetooth_link'} if now==101. else set()),(now,width,tiles)
                        assert previous is None or tiles==previous,(width,previous,tiles)
                        previous=tiles
    finally:
        window.setGeometry(original);window.page_turns=turns;window._compact_cache=window._compact_surface=None;window.grab()
    checks.append('Music, AI provider badges, agenda and all reminder families keep their painted bounds during resize. Mail, face, pet, system gauges and nine device indicators stay compact; device changes still expand for five seconds.')
