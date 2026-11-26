"""Exercise new indicator, edge, stopwatch and alarm paths on the private desktop."""
import copy
from datetime import datetime
import time
from unittest.mock import patch

from PyQt5.QtCore import Qt
from ui_test_events import Events as QTest


def wait_for(condition,seconds=2):
    end=time.monotonic()+seconds
    while not condition() and time.monotonic()<end:QTest.qWait(25)
    return condition()


def check_device_sources(indicators):
    import ctypes
    from unittest.mock import Mock
    from device_alert_readings import AudioSwitchRead, BRIGHTNESS, BrightnessNotifications, PowerSetting
    from device_status import GUID
    worker=AudioSwitchRead({'microphone','volume'})
    source=Mock()
    source.microphone_enabled.side_effect=[True,True,False]
    source.volume.side_effect=[(33,False),(33,False),(33,True)]
    observed=[]
    worker.changed.connect(lambda kind,value:observed.append((kind,value)))
    waits=[]
    def tick(interval):
        waits.append(interval)
        if len(waits)==3:worker.requestInterruption()
    with patch('device_alert_readings.DeviceStatus',return_value=source),patch.object(worker.cancelled,'wait',tick):
        worker.run()
    assert [v for k,v in observed if k=='microphone']==[True,False]
    assert [v for k,v in observed if k=='volume']==[(33,False),(33,True)] and waits==[.2]*3
    worker.deleteLater()

    sensor=BrightnessNotifications();readings=[]
    sensor.changed.connect(readings.append)
    info=PowerSetting(GUID.from_buffer_copy(BRIGHTNESS),4,0)
    for value in (0,82,101):
        info.percent=value
        sensor.receive(None,0x8013,ctypes.addressof(info))
    info.percent=22;info.length=1
    sensor.receive(None,0x8013,ctypes.addressof(info))
    sensor.close()
    assert readings==[0,82]
    from PyQt5.QtGui import QColor,QPen
    from capsule_indicators import draw_brightness_sun,draw_volume_speaker
    for level,rays,waves in ((0,0,0),(1,1,1),(25,2,1),(26,3,2),(50,4,2),(51,5,3),(75,6,3),(76,7,4),(100,8,4)):
        painter=Mock();painter.pen.return_value=QPen(QColor('#8b651a'))
        draw_brightness_sun(painter,level,3)
        alphas=[call.args[0].color().alpha() for call in painter.setPen.call_args_list]
        assert painter.drawEllipse.call_count==1 and painter.drawLine.call_count==8
        assert alphas.count(255)==rays and all(alpha>=100 for alpha in alphas)
        painter.reset_mock();draw_volume_speaker(painter,(level,False),3)
        alphas=[call.args[0].color().alpha() for call in painter.setPen.call_args_list]
        assert painter.drawArc.call_count==4 and alphas.count(255)==waves and all(alpha>=100 for alpha in alphas)

    # The firmware can disable the touch surface while Windows still says on.
    native=Mock();native.touchpad.return_value=True
    with patch.object(indicators,'native',native),patch.object(indicators,'touchpad_source','pending'):
        indicators.read_touchpad()
        assert indicators.values['touchpad']=='pending' and 'touchpad' not in indicators.transitions
        for source,enabled in (('off',False),('on',True)):
            indicators.touchpad_source=source;indicators.read_touchpad(changed=True)
            assert indicators.values['touchpad'] is enabled and 'touchpad' in indicators.transitions
        native.touchpad.return_value=False
        indicators.read_touchpad()
        assert indicators.values['touchpad'] is False
        indicators.observe('touchpad',None)


def check_right_clock(window,cfg,output):
    import resource_compact as compact
    from resource_runner import capsule_rect
    with patch.dict(cfg,resource_clock=True,resource_clock_format='date_seconds',resource_runner_enabled=True,
                    resource_compact_auto_width=False):
        for shape in ('pill','bar'):
            cfg['resource_fold']=shape
            window._compact_cache=None
            assert compact.plan(window,96)['clock']==('%Y-%m-%d','%H:%M:%S')
            layout=compact.plan(window,window.width());window._compact_surface=None
            with patch.object(compact,'draw_clock',wraps=compact.draw_clock) as draw:
                frame=window.grab()
            draw.assert_called_once()
            rect, rows=draw.call_args.args[1:3]
            assert rect.right()==window.width()-8 and rect.width()==layout['clock_width']
            assert len(rows)==2 and rows[0] and rows[1].count(':')==2
            clock_left=rect.left()
            assert layout['runner_width'] and capsule_rect(window).right()<clock_left
            bounds=window.compact_bounds+window.reminder_bounds+list(window.status_bounds.values())
            assert all(rect.right()<=clock_left for rect in bounds)
            assert frame.save(str(output/('capsule-clock-right-'+shape+'.png')))
    window._compact_cache=None;window._compact_surface=None


def run(api,runtime,app,output,checks):
    from capsule_indicators import GROW,HOLD,SHRINK
    from desktop_edge_reveal import EdgeReveal
    from resource_compact import plan
    from resource_options import DEFAULTS,DEVICE_ALERTS
    from resource_pomodoro import DEFAULT_STATE,read_state
    from resource_settings import ResourceOptions
    cfg=runtime.dock.cfg;service=runtime.resources;before=copy.deepcopy(cfg)
    previous_auto=service.auto_compact
    model=old_clock=old_state=None
    try:
        assert DEFAULTS['resource_edge_hide'] is False and api.normalize_features({})['card_edge_hide'] is False
        service.auto_compact=None
        cfg.update(resource_enabled=True,resource_collapsed=True,resource_fold='pill',resource_edge='right',
                   resource_edge_snap=True,card_snap=True,resource_capsule_taskbar=False,resource_edge_hide=False,
                   resource_compact_width=500,resource_compact_auto_width=True,resource_halo=False,
                   motion_enabled=True,resource_expand_mode='click',resource_face=True,resource_auto_hide=False,
                   resource_pomodoro=True,resource_alert_alarm=True,resource_alert_stopwatch=True,
                   resource_compact_metrics=[],resource_alert_almanac=False,resource_alert_focus=False,
                   resource_alert_agenda=False,resource_clock=False,resource_water_enabled=False,
                   resource_runner_enabled=False,resource_mail_icon=False,resource_component_locations={})
        cfg.update({'resource_alert_'+k:False for k in DEVICE_ALERTS})
        service.sync();window=service.window;app.processEvents()
        settings=ResourceOptions(service)
        try:
            for key in DEVICE_ALERTS:settings.fields['resource_alert_'+key].setChecked(True)
            assert settings.commit()
        finally:settings.deleteLater()
        indicators=service.indicators;now=[40.]
        data={'caps_lock':False,'input_mode':'en','num_lock':True,'microphone':True,'touchpad':True,
              'bluetooth_link':(),'network_link':(),'volume':(32,False),'brightness':45}
        with patch.object(indicators,'clock',lambda:now[0]):
            for key,value in data.items():indicators.observe(key,value)
            assert not indicators.transitions and len(plan(window,window.width())['devices'])==9
            assert window.grab().save(str(output/'capsule-status-icons.png'))
            indicators.observe('caps_lock',True)
            assert indicators.fraction('caps_lock',now[0])==0
            now[0]+=GROW/2
            assert 0<indicators.fraction('caps_lock',now[0])<1
            indicators.observe('microphone',False);indicators.observe('bluetooth_link',(('test','蓝牙耳机'),))
            now[0]+=GROW+.01;indicators.advance()
            rows=plan(window,window.width())['devices']
            assert any(key=='bluetooth_link' and '耳机' in label and width>side for key,side,width,label in rows)
            assert window.grab().save(str(output/'capsule-status-expanded.png'))
            now[0]+=HOLD-.3
            indicators.observe('microphone',True)
            now[0]+=.6;indicators.advance()
            assert set(indicators.transitions)=={'microphone'}
            now[0]+=HOLD+SHRINK;indicators.advance()
            assert not indicators.transitions and not indicators.frame.isActive()
            indicators.observe('touchpad',None);indicators.observe('touchpad',False)
            assert not indicators.transitions and indicators.values['touchpad'] is False
            indicators.observe('volume',(0,False));indicators.observe('brightness',0)
            now[0]+=GROW+.01;indicators.advance()
            labels={k:label for k,side,width,label in plan(window,window.width())['devices'] if width>side}
            assert labels.get('volume')==labels.get('brightness')=='0'
            sizes=[(side,width) for k,side,width,_ in indicators.cells(450,30) if k in ('volume','brightness')]
            now[0]+=2
            indicators.observe('volume',(42,False));indicators.observe('brightness',82)
            now[0]+=GROW+.01;indicators.advance()
            assert indicators.transitions['volume'][2]=='系统音量 42%' and indicators.transitions['brightness'][2]=='屏幕亮度 82'
            assert ('volume','42') in [(key,label) for key,_,_,label in plan(window,window.width())['devices']]
            assert sizes==[(side,width) for k,side,width,_ in indicators.cells(450,30) if k in ('volume','brightness')]
            check_right_clock(window,cfg,output)
            now[0]+=3
            indicators.observe('volume',(42,True))
            assert indicators.transitions['volume'][2]=='系统音量已静音'
            assert ('volume','0') in [(key,label) for key,_,_,label in plan(window,window.width())['devices']]
            now[0]+=2;indicators.advance()
            assert set(indicators.transitions)=={'volume'}
            now[0]+=HOLD;indicators.advance()
            assert all(width==side and not label for _,side,width,label in plan(window,window.width())['devices'])
            check_device_sources(indicators)
            for kind,value in (('input_mode','zh'),('num_lock',False),('network_link',(('WLAN','测试网络'),))):
                indicators.observe(kind,value)
                assert kind in indicators.transitions
        checks.append('Nine device states: five-second numeric badges, fixed icon and number widths, four volume waves, eight always-visible brightness rays, muted audio, power packets and firmware touchpad events.')
        checks.append('Date and seconds stay at the right edge of compact pills and bars with device labels and the pet, including reserved clock space at 96 pixels.')

        from folding_tests import sample_transition
        from resource_resize_tests import visit_options
        assert service.set_options(resource_edge='free')
        for shape in ('bar','pill','ball'):
            assert service.set_options(resource_fold=shape)
            assert service.fold(False)
            sample_transition(window,output/('fold-resource-'+shape+'.png'))
            assert service.fold(True,automatic=True)
            sample_transition(window)
            def check_compact(dialog):
                assert service.compact and window.fold_shape()==shape
                assert not window.detail.isVisible() and window._fold_surface is None
            visit_options(service.settings,check_compact)
            check_compact(None)
        notice=('mail_new','2 封新邮件')
        service.peek_reminder(notice)
        assert window.compact_notice==notice and window.fold_shape()=='pill' and not window.detail.isVisible()
        sample_transition(window,output/'fold-resource-notice.png')
        assert window.width()<=280 and window.reminder_kinds==['mail_new']
        assert window.notice_timer.isActive() and window.notice_timer.interval()==5000
        assert service.reminders()[0]==notice
        second=('quota_notice','周额度已接近上限')
        service.peek_reminder(second);sample_transition(window)
        assert service.reminders()[0]==second and notice not in service.reminders()
        assert wait_for(lambda:window.compact_notice is None,5.5)
        assert wait_for(lambda:window._fold_surface is None)
        assert window.fold_shape()=='ball' and service.compact and cfg['resource_fold']=='ball'
        service.peek_reminder(notice);assert service.fold(False)
        sample_transition(window)
        assert not window.notice_timer.isActive() and window.compact_notice is None
        service.peek_reminder(second);assert not window.notice_timer.isActive()
        assert service.fold(True);sample_transition(window)
        cfg['motion_enabled']=False
        service.peek_reminder(notice);assert window._fold_surface is None and window.notice_timer.isActive()
        window.present_notice(None);assert window.fold_shape()=='ball' and window._fold_surface is None
        cfg['motion_enabled']=True
        checks.append('Animated capsule opening and folding for each shape, with compact notification replacement, a five-second return to the selected ball, and explicit opening during a reminder.')

        assert service.set_options(resource_edge_hide=True,resource_fold='ball',resource_edge='right')
        edge=window.edge_reveal
        indicators.observe('touchpad',False)
        with patch.object(edge,'visible_at_cursor',return_value=False):
            edge.settle();wait_for(lambda:edge.fraction==0.)
            mask=window.mask().boundingRect()
            assert edge.fraction==0. and not mask.isEmpty() and min(mask.width(),mask.height())<=7, (
                edge.edge,edge.find_edge(),edge.target,edge.fraction,window.geometry().getRect(),mask.getRect(),
                cfg['resource_edge'],window.isWindow(),service.editing,edge.peek_until)
            assert edge.light.grab().save(str(output/'capsule-edge-light.png'))
            def notify_while_editing(dialog):
                edge.settle()
                assert edge.fraction==0. and edge.find_edge()=='right' and edge.light.isVisible()
                service.peek_reminder(('mail_new','新邮件'))
                edge.animation.setCurrentTime(edge.animation.duration()//2)
                partial=window.mask().boundingRect()
                assert 0.<edge.fraction<1. and mask.width()<partial.width()<window.width()
                edge.animation.setCurrentTime(edge.animation.duration())
            visit_options(service.settings,notify_while_editing)
            indicators.observe('touchpad',True);wait_for(lambda:edge.fraction==1.)
            assert edge.fraction==1. and service.compact and window.fold_shape()=='pill', (
                edge.target,edge.fraction,edge.as_pill,edge.peek_until,service.compact,window.fold_shape())
            assert not window.detail.isVisible() and window.mask().isEmpty()
            QTest.qWait(max(1,int(1000*(edge.peek_until-time.monotonic()-.5))))
            assert edge.fraction==1. and service.compact
            assert wait_for(lambda:edge.fraction==0.,3) and window.fold_shape()=='ball'
            edge.move_to(1.);assert wait_for(lambda:edge.fraction==1.)
        assert service.set_options(resource_edge_hide=False,resource_fold='pill',**{'resource_alert_'+k:False for k in DEVICE_ALERTS})
        assert not indicators.selected and not indicators.poll.isActive() and not indicators.link_timer.isActive()
        assert window.mask().isEmpty()
        from PyQt5.QtWidgets import QWidget
        card=QWidget();card.setWindowFlags(Qt.Tool);card.resize(100,76)
        area=app.primaryScreen().availableGeometry();card.move(area.topLeft());card.show()
        try:
            controller=EdgeReveal(card,runtime,False);controller.configure(True);controller.edge='top'
            controller.move_to(0.);assert wait_for(lambda:controller.fraction==0.);controller.notify()
            assert controller.fraction==0. and not controller.peek_until
            controller.configure(False);assert card.mask().isEmpty()
        finally:card.close();card.deleteLater()
        checks.append('Edge hiding defaults off. An edge-docked ball shows only the light strip, opens as a compact pill on a device event, and returns after five real seconds. A desktop card stays hidden during reminders.')

        model=service.get_pomodoro();old_state=copy.deepcopy(model.state);old_clock=model.clock
        clock=[datetime(2026,11,25,18,20,10).timestamp()];model.clock=lambda:clock[0]
        model.state=dict(DEFAULT_STATE);model.sync()
        assert service.fold(False);window.select_page('pomodoro');app.processEvents()
        page=window.view('pomodoro').content;page.tab_buttons[1].click()
        page.watch_toggle.click();clock[0]+=75;model.sync()
        assert page.watch_value.text()=='01:15'
        from PyQt5.QtCore import QTime
        page.alarm_time.setTime(QTime(18,22));page.repeat.setChecked(True);page.arm.click()
        assert window.grab().save(str(output/'capsule-stopwatch-alarm.png'))
        assert service.fold(True);window.grab()
        assert ('stopwatch','01:15') in service.reminders() and ('alarm','18:22') in service.reminders()
        assert {'stopwatch','alarm'}<=set(window.reminder_kinds)
        assert window.grab().save(str(output/'capsule-timers-compact.png'))
        model.toggle_stopwatch();clock[0]+=36
        with patch.object(runtime.dock,'preview',False),patch.object(runtime.tray,'showMessage') as notify,patch.object(service,'play_reminder_sound') as sound:
            model.sync();model.sync()
            assert notify.call_count==1 and sound.call_count==1
        assert model.elapsed()==75 and ('alarm_due','18:22') in model.badges()
        assert datetime.fromtimestamp(model.state['alarm_at']).day==26
        assert read_state(model.path)['alarm_at']==model.state['alarm_at']
        model.dismiss_alarm();model.cancel_alarm();model.toggle_stopwatch();clock[0]+=3
        assert model.elapsed()==78;model.reset_stopwatch()
        model.arm_alarm('18:23',False);clock[0]+=60;model.sync()
        assert model.state['alarm_due'] and not model.state['alarm_at']
        checks.append('Stopwatch and one-time/daily alarms use real controls and compact chips. Time survives fold, pause and resume, daily alarms reschedule once, dismissed alarms and resets persist.')
    finally:
        if model and old_state is not None:
            model.clock=old_clock;model.save(old_state);model.timer.stop()
        service.auto_compact=previous_auto
        cfg.clear();cfg.update(before);service.sync();api.save_config(cfg);app.processEvents()
