"""Native status card, timer persistence, and collapsed reminder regression."""
import copy
from datetime import datetime
import json
import tempfile
from pathlib import Path
import time
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch
import wave

from PyQt5.QtCore import QDate, QDateTime, QEvent, QPointF, QRectF, QTimer, Qt
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtWidgets import QApplication, QBoxLayout, QDateTimeEdit, QLineEdit, QPlainTextEdit, QPushButton


def audio_regressions(api,service,checks):
    from resource_reminder_audio import CUE_SPACING_MS, SOUND_DIR, SOUND_KINDS, winsound
    from resource_settings import ResourceOptions

    waveforms=set()
    for kind in SOUND_KINDS:
        with wave.open(str(SOUND_DIR / (kind + '.wav')),'rb') as sound:
            duration=1000*sound.getnframes()/sound.getframerate()
            assert 100<=duration<=200<CUE_SPACING_MS
            assert (sound.getnchannels(),sound.getsampwidth(),sound.getcomptype())==(1,2,'NONE')
            waveforms.add(sound.readframes(sound.getnframes()))
    assert len(waveforms)==len(SOUND_KINDS)==6

    settings=ResourceOptions(service)
    switch=settings.fields['resource_reminder_sound']
    assert switch.isChecked()
    flags=winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
    with patch.object(winsound,'PlaySound') as playback:
        try:
            service.play_reminder_sound('agenda')
            with patch.object(service.runtime.dock,'preview',False),patch.object(service.runtime,'game_active',True):
                service.play_reminder_sound('agenda')
            playback.assert_not_called()
            with patch.object(service.runtime.dock,'preview',False):
                for kind in ('agenda','water','agenda','battery','water'):
                    service.play_reminder_sound(kind)
            player=service.reminder_audio
            playback.assert_called_once_with(str(SOUND_DIR / 'agenda.wav'),flags)
            assert list(player.pending)==['water','battery'] and player.timer.isActive()
            player.timer.stop();player.timer.timeout.emit()
            assert playback.call_args.args==(str(SOUND_DIR / 'water.wav'),flags)
            switch.setChecked(False)
            assert settings.commit() and api.load_config()['resource_reminder_sound'] is False
            assert playback.call_args.args==(None,0) and not player.pending and not player.timer.isActive()
            player.timer.timeout.emit()
            with patch.object(service.runtime.dock,'preview',False):
                service.play_reminder_sound('agenda')
            assert playback.call_count==3
            switch.setChecked(True)
            assert settings.commit() and api.load_config()['resource_reminder_sound'] is True
            assert playback.call_count==3
            with patch.object(service.runtime.dock,'preview',False):
                service.play_reminder_sound('quota')
            assert playback.call_args.args==(str(SOUND_DIR / 'quota.wav'),flags) and playback.call_count==4
        finally:
            if service.reminder_audio:service.reminder_audio.stop()
            settings.reject();settings.deleteLater()
    checks.append('Six distinct bundled WAV cues last 100-200 ms. Playback queues different kinds and coalesces duplicates. The saved sound switch stops playback and clears the queue. Preview and pause stay silent.')


def run(api,runtime,app,output,checks):
    from bluetooth_gauge import devices
    from device_status import DeviceStatus, battery_status
    from resource_pomodoro import DEFAULT_STATE, Pomodoro, read_state
    from resource_options import DEFAULTS
    from resource_system_view import battery_ink
    service=runtime.resources;cfg=runtime.dock.cfg;before=copy.deepcopy(cfg)
    audio_regressions(api,service,checks)
    previous_model=service.pomodoro;service.pomodoro=None
    if previous_model:previous_model.timer.stop()
    previous_agenda=service.agenda;service.agenda=None
    if previous_agenda:previous_agenda.timer.stop()
    model=agenda=None

    assert battery_status(1,8,62)==(62,'charging')
    assert battery_status(1,128,255)==(None,'ac')
    assert battery_status(1,1,100)==(100,'full')
    assert battery_status(255,255,255)==(None,'unknown')
    assert battery_ink(12,'battery',True,'#888888')!=battery_ink(12,'charging',True,'#888888')
    reader=DeviceStatus.__new__(DeviceStatus);reader.connection_cache=None
    with patch.object(reader,'network_profile',side_effect=('办公无线','')):
        assert reader.connection_name(b'wireless','Wi-Fi',20)=='办公无线'
        assert reader.connection_name(b'wireless','Wi-Fi',24)=='办公无线'
        assert reader.connection_name(b'wireless','Wi-Fi',26)=='Wi-Fi'
    try:
        cfg['resource_enabled']=False;service.sync()
        with tempfile.TemporaryDirectory(prefix='fishdock-pomodoro-') as folder:
            cfg.update(copy.deepcopy(DEFAULTS))
            cfg.update(resource_enabled=True,resource_collapsed=False,resource_auto_hide=False,
                       resource_open_page='resources',resource_bluetooth=True,resource_face=True,resource_cpu_power=True,
                       resource_expanded_width=620,resource_expanded_height=340,
                       resource_focus_minutes=25,resource_water_interval=45,
                       resource_background='custom',resource_appearance=dict(material='liquid',theme='light',
                           color='',opacity=52,blur=8,highlight=45))
            service.sync()
            window=service.window
            window.select_page('resources')
            now=time.monotonic()
            assert 'system_status' in service.active_keys() and 'brightness' in service.sensors.keys
            sensors=service.sensors
            sensors.values['cpu_power']={'value':8,'source':'演示数据','label':'CPU 封装功率'}
            service.sensors.values['brightness']={'value':76,'source':'Windows WMI','label':'亮度'}
            service.bluetooth.publish(devices([dict(id='00000000001A',name='BOW5.0',level=79)]),'')
            service.accept_sample(dict(time=now,cpu=18,memory=(64,10.2*2**30,16*2**30),gpu=22,network=(393216,83968),
                system_status=dict(battery=(62,'charging'),volume=(44,False),connection='办公无线')))
            app.processEvents()
            status=window.system_readout.accessibleName()
            assert all(value in status for value in ('62%','充电中','44%','76%','办公无线')) and 'bps' not in status
            assert window.rings.height()==17 and window.rings.parent() is window.battery_section
            assert window.sensor_columns.geometry().top()==window.battery_section.geometry().top()
            assert window.sensor_columns.height()==window.battery_section.height()
            assert window.graph.height()==window.rank_section.height()
            assert window.battery_section.grab().save(str(output/'readme-device-status.png'))
            assert window.grab().save(str(output/'device-status-expanded.png'))
            service.latest['system_status']=dict(battery=(12,'battery'),volume=(44,True),connection='')
            service.sensors.values.pop('brightness');service.display();app.processEvents()
            assert all(value in window.system_readout.accessibleName() for value in ('12%','静音','亮度 —','未连接'))
            assert window.battery_section.grab().save(str(output/'device-status-low.png'))

            from resource_compact import compact_badges,plan,status_values
            from resource_options import COMPACT_DEVICE
            from resource_settings import ResourceOptions
            previous_metrics=list(cfg['resource_compact_metrics'])
            previous_pins=list(cfg['resource_compact_pinned'])
            options=ResourceOptions(service);options.tabs.setCurrentIndex(2)
            for key in COMPACT_DEVICE:options.compact_fields[key].setChecked(True)
            fmt=options.fields['resource_clock_format'];fmt.setCurrentIndex(fmt.findData('date_seconds'))
            assert options.commit()
            assert set(COMPACT_DEVICE)<=set(cfg['resource_compact_metrics'])
            assert not set(COMPACT_DEVICE)&set(cfg['resource_compact_pinned'])
            assert api.load_config()['resource_clock_format']=='date_seconds'
            options.deleteLater()
            assert service.fold(True)
            assert {'battery','connection','volume'}<=service.active_keys() and 'system_status' not in service.active_keys()
            assert 'brightness' in service.sensors.keys
            service.sensors.values['brightness']={'value':76,'source':'演示数据','label':'亮度'}
            service.accept_sample(dict(time=time.monotonic(),battery=(62,'charging'),volume=(44,False),connection='办公无线'))
            status={key:value for key,_,value,_ in status_values(service)}
            assert {key:status[key] for key in COMPACT_DEVICE}==dict(battery='62%',connection='办公无线',volume='44%',brightness='76%')
            layout=plan(window,window.width())
            assert layout['clock']==('%Y-%m-%d','%H:%M:%S')
            assert window.grab().save(str(output/'readme-compact-status.png'))
            assert set(window.status_bounds)=={*COMPACT_DEVICE,'bluetooth'}
            assert not set(window.compact_shown)&set(window.status_bounds)
            for rect in window.status_bounds.values():
                assert QRectF(window.rect()).contains(rect)
                assert rect.center().y()==window.height()/2
                assert not any(rect.intersects(bounds) for bounds in window.compact_bounds)
            assert service.set_options(resource_compact_metrics=previous_metrics,resource_compact_pinned=previous_pins,resource_clock_format='time')
            assert not ({'battery','connection','volume'} & service.active_keys()) and 'brightness' not in service.sensors.keys
            assert service.fold(False)

            clock=[datetime(2026,11,9,14,0).timestamp()]
            model=service.pomodoro=Pomodoro(service,lambda:clock[0])
            model.path=Path(folder)/'timer.json'
            model.state=dict(DEFAULT_STATE);model.changed.connect(service.reminders_changed)
            window.select_page('pomodoro');app.processEvents()
            assert 'system_status' not in service.active_keys() and (not service.sensors or 'brightness' not in service.sensors.keys)
            assert service.sensors is sensors and sensors.values['cpu_power']['value']==8
            page=window.view('pomodoro').content
            assert page.toggle.text()=='开始' and not page.water_switch.isChecked()
            page.water_switch.click();assert cfg['resource_water_enabled'] and model.water()[3]>clock[0]
            page.drink.click();page.drink.click();assert model.water()[1]==500
            page.undo.click();assert model.water()[1]==250
            page.drink.click();assert model.water()[1]==500
            page.toggle.click();assert model.focus()[1:3]==('running',1500)
            clock[0]+=53;model.sync()
            assert model.focus()[2]==1447 and read_state(model.path)['status']=='running'
            from resource_pomodoro_view import reminder_icon
            with patch('resource_pomodoro_view.reminder_icon',wraps=reminder_icon) as marks:
                page.focus_summary.grab();page.water_summary.grab()
            focus_ring,water_ring=[call.args[1:3] for call in marks.call_args_list]
            assert focus_ring[0].center()==water_ring[0].center() and water_ring[1]=='water'
            assert service.set_options(resource_compact_metrics=[*previous_metrics,'pomodoro','water'],
                                       resource_compact_pinned=[*previous_pins,'pomodoro','water'],
                                       resource_alert_focus=False,resource_alert_water=False)
            assert service.fold(True)
            clock[0]+=1;model.sync();window.grab()
            compact,active=compact_badges(service)
            assert active==0 and dict(compact)=={'focus':'24:06','water':'500 mL'}
            window.grab();assert set(window.reminder_kinds)=={'focus','water'}
            assert model.timer.remainingTime()<=1100
            clock[0]-=1
            assert service.fold(False)
            window.select_page('pomodoro');app.processEvents()
            assert service.set_options(resource_compact_metrics=previous_metrics,resource_compact_pinned=previous_pins,
                                       resource_alert_focus=True,resource_alert_water=True)
            before_width,before_height=window.width(),window.height()
            window.resize(before_width,190);app.processEvents()
            assert window.grab().save(str(output/'readme-pomodoro.png'))
            window.resize(290,before_height);app.processEvents()
            assert page.cards.direction()==QBoxLayout.TopToBottom
            assert window.view('pomodoro').verticalScrollBar().maximum()<=2
            for summary,action in ((page.focus_summary,page.toggle),(page.water_summary,page.drink)):
                assert summary.geometry().bottom()<action.geometry().top()
                assert action.geometry().bottom()<summary.parentWidget().height()
            assert window.grab().save(str(output/'pomodoro-narrow.png'))
            window.resize(before_width,before_height);app.processEvents()
            assert page.cards.direction()==QBoxLayout.LeftToRight

            page.toggle.click();assert page.toggle.text()=='继续'
            clock[0]+=45*60
            with patch.object(runtime.dock,'preview',False),patch.object(runtime.tray,'showMessage') as notify,patch.object(service,'play_reminder_sound') as sound:
                model.sync();model.sync()
                notify.assert_called_once()
                sound.assert_called_once_with('water')
            assert model.focus()[2]==1447 and model.badges()==(('water','喝水'),('paused','24:07'))
            assert service.set_options(resource_alert_water=False,resource_alert_focus=False)
            assert not model.badges() and model.water()[4] and model.focus()[1]=='paused'
            assert service.set_options(resource_alert_water=True,resource_alert_focus=True)
            page.toggle.click();assert model.focus()[1]=='running'
            assert service.fold(True);app.processEvents();window.grab()
            assert len(window.reminder_bounds)==2
            assert window.grab().save(str(output/'readme-pomodoro-compact.png'))
            point=window.reminder_bounds[0].center()
            global_point=QPointF(window.mapToGlobal(point.toPoint()))
            for kind,buttons in ((QEvent.MouseButtonPress,Qt.LeftButton),(QEvent.MouseButtonRelease,Qt.NoButton)):
                app.sendEvent(window,QMouseEvent(kind,point,global_point,Qt.LeftButton,buttons,Qt.NoModifier))
            assert not service.compact and window.page_key=='pomodoro'
            page.delay.click();assert not model.water()[4]
            clock[0]+=1448
            with patch.object(runtime.dock,'preview',False),patch.object(runtime.tray,'showMessage') as notify,patch.object(service,'play_reminder_sound') as sound:
                model.sync();model.sync()
                notify.assert_called_once()
                sound.assert_called_once_with('focus_done')
            assert model.badges()==(('focus_done','完成'),)
            assert service.set_options(resource_fold='ball') and service.fold(True)
            app.processEvents();assert window.grab().save(str(output/'pomodoro-ball.png'))
            page.rest_button.click();assert model.focus()==('rest','idle',300,300)
            model.toggle()
            clock[0]+=300
            with patch.object(runtime.dock,'preview',False),patch.object(runtime.tray,'showMessage') as notify,patch.object(service,'play_reminder_sound') as sound:
                model.sync();model.sync()
                notify.assert_called_once()
                sound.assert_called_once_with('rest_done')
            clock[0]+=86400;model.sync()
            assert model.water()[1]==0 and model.water()[3]>clock[0]
            assert service.set_options(resource_pomodoro=False)
            assert not model.timer.isActive() and not window.page_enabled('pomodoro') and not model.badges()

            assert service.set_options(resource_fold='pill',resource_alert_battery=True)
            assert service.fold(False)
            clock[0]=datetime(2026,11,9,11,23).timestamp()
            agenda=service.get_agenda();agenda.clock=lambda:clock[0]
            window.select_page('agenda');app.processEvents()
            agenda_page=window.view('agenda').content
            start=int(clock[0]+300);end=start+3600
            errors=[]
            def fill_agenda():
                modal=QApplication.activeModalWidget()
                try:
                    assert modal.windowTitle()=='新增日程'
                    title=next(field for field in modal.findChildren(QLineEdit) if field.accessibleName()=='标题')
                    title.setText('项目周会')
                    starts,ends=modal.findChildren(QDateTimeEdit)
                    starts.setDateTime(QDateTime.fromSecsSinceEpoch(start))
                    ends.setDateTime(QDateTime.fromSecsSinceEpoch(end))
                    save=next(b for b in modal.findChildren(QPushButton) if b.text()=='保存')
                    point=save.rect().center()
                    assert modal.childAt(save.mapTo(modal,point)) is save
                    assert modal.grab().save(str(output/'agenda-editor.png'))
                    for kind,buttons in ((QEvent.MouseButtonPress,Qt.LeftButton),(QEvent.MouseButtonRelease,Qt.NoButton)):
                        app.sendEvent(save,QMouseEvent(kind,QPointF(point),Qt.LeftButton,buttons,Qt.NoModifier))
                except Exception as error:
                    errors.append(error)
                finally:
                    if modal and modal.isVisible():modal.reject()
            QTimer.singleShot(50,fill_agenda)
            agenda_page.add_button.click()
            assert not errors,errors
            assert agenda.events[0]['title']=='项目周会' and agenda.events[0]['start']==start
            from ui_style import ModernComboBox
            from resource_agenda_import import parse_response,merge_import
            ding_time=lambda stamp:dict(dateTime=datetime.fromtimestamp(stamp).astimezone().isoformat())
            ding=dict(events=[dict(id='ding-sample',summary='设备调试复盘',start=ding_time(start+4*3600),end=ding_time(end+4*3600))])
            fei=dict(code=0,data=dict(items=[dict(event_id='fei-sample',summary='设计评审',
                     start_time=dict(timestamp=str(start+2*3600)),end_time=dict(timestamp=str(end+2*3600)))]))
            probe,skipped,more=parse_response('feishu',json.dumps(fei))
            assert len(probe)==1 and not skipped and not more and probe[0]['source']=='feishu'
            probe[0]['ack']=True
            refreshed=parse_response('feishu',json.dumps(fei))[0]
            assert merge_import(probe,refreshed)[0]['ack']
            options=ResourceOptions(service);options.tabs.setCurrentIndex(9)
            errors=[]
            def import_samples():
                modal=QApplication.activeModalWidget()
                try:
                    combo=modal.findChild(ModernComboBox)
                    editor=modal.findChild(QPlainTextEdit)
                    action=next(b for b in modal.findChildren(QPushButton) if b.text()=='导入日程')
                    for source,payload in (('dingtalk',ding),('feishu',fei),('feishu',fei)):
                        combo.setCurrentIndex(combo.findData(source))
                        editor.setPlainText(json.dumps(payload,ensure_ascii=False));action.click()
                        assert not editor.toPlainText()
                except Exception as error:
                    errors.append(error)
                finally:
                    if modal:modal.reject()
            def open_manual_import():
                connections=QApplication.activeModalWidget()
                try:
                    assert connections.windowTitle()=='日程账号接入'
                    assert '用钉钉扫码' in connections.steps.text()
                    assert connections.steps.height()>=connections.steps.heightForWidth(connections.steps.width())
                    connections.source.setCurrentIndex(connections.source.findData('feishu'))
                    app.processEvents()
                    assert '用飞书扫码' in connections.steps.text()
                    assert connections.steps.height()>=connections.steps.heightForWidth(connections.steps.width())
                    assert not connections.findChildren(QLineEdit)
                    assert connections.grab().save(str(output/'calendar-settings.png'))
                    sync=connections.sync
                    cancelled=Event()
                    sync.job=SimpleNamespace(source='feishu',connecting=True,signed_in=False,cancelled=cancelled,
                                             requestInterruption=cancelled.set)
                    try:
                        sync.scan_info=('feishu','feishu-app','https://open.feishu.cn/page/launcher?fixture=1')
                        connections.update_status();app.processEvents()
                        assert connections.qr.isVisible() and not connections.qr.pixmap().isNull()
                        scan_height=connections.height()
                        assert connections.grab().save(str(output/'calendar-scan.png'))
                        connections.source.setCurrentIndex(connections.source.findData('dingtalk'))
                        assert connections.qr.isHidden()
                        sync.job.source='dingtalk'
                        sync.transfer=('dingtalk','download',8*1024**2,24*1024**2)
                        connections.update_status();app.processEvents()
                        assert connections.progress.isVisible() and connections.progress.value()==8*1024**2
                        assert '8.0 / 24.0 MB' in connections.status.text() and '33%' in connections.status.text()
                        assert connections.height() < scan_height
                        assert connections.connect_account.text()=='取消下载'
                        assert connections.grab().save(str(output/'calendar-download.png'))
                        connections.connect_account.click()
                        assert sync.job.cancelled.is_set() and connections.progress.isHidden()
                        sync.job=SimpleNamespace(source='tencent',connecting=True,signed_in=False,cancelled=Event())
                        connections.source.setCurrentIndex(connections.source.findData('tencent'))
                        sync.scan_info=('tencent','tencent','https://meeting.tencent.com/marketplace/tencentmeeting-cli-auth.html?code=fixture')
                        connections.update_status();app.processEvents()
                        assert connections.qr.isVisible() and '腾讯会议' in connections.status.text()
                    finally:
                        sync.job=None;sync.scan_info=None;sync.transfer=None;connections.update_status()
                    QTimer.singleShot(50,import_samples)
                    next(b for b in connections.findChildren(QPushButton) if b.text()=='手动导入…').click()
                except Exception as error:
                    errors.append(error)
                finally:
                    if connections:connections.reject()
            QTimer.singleShot(50,open_manual_import)
            next(b for b in options.findChildren(QPushButton) if b.text()=='日程账号接入…').click()
            assert not errors,errors
            options.deleteLater()
            assert api.load_config()['resource_agenda_events'][0]['title']=='项目周会'
            assert {event['source'] for event in agenda.events}=={'local','dingtalk','feishu'}
            from resource_tencent_login import meeting_rows
            meetings=meeting_rows([dict(meeting_id='fixture',subject='版本验收会议',start_time=start+3*3600,
                                        end_time=end+3*3600),
                                  dict(meeting_id='tomorrow',subject='项目演示',start_time=start+86400,
                                        end_time=end+86400)],start-3600,end+2*86400)
            assert agenda.save(merge_import(agenda.local_events,meetings))
            agenda_page.calendar.setSelectedDate(QDateTime.fromSecsSinceEpoch(start).date())
            day=agenda_page.calendar.selectedDate()
            assert agenda_page.rows.count()==4 and agenda_page.reminder.isVisible(),(agenda_page.rows.count(),window.page_key)
            assert agenda_page.calendar.markers[day.toPyDate()]=={'local','dingtalk','feishu','tencent'}
            assert not agenda_page.calendar.markers.get(day.addDays(-1).toPyDate())
            assert agenda_page.calendar.markers[day.addDays(1).toPyDate()]=={'tencent'}
            agenda_page.next_month.click()
            assert agenda_page.calendar.monthShown()==day.addMonths(1).month()
            today=QDate.currentDate()
            agenda_page.calendar.setSelectedDate(today.addMonths(-1))
            agenda_page.today.click()
            assert agenda_page.calendar.selectedDate()==today
            assert agenda_page.calendar.monthShown()==today.month()
            agenda_page.calendar.setSelectedDate(day)
            original_height=window.height();window.resize(window.width(),260);app.processEvents()
            last=agenda_page.rows.visualItemRect(agenda_page.rows.item(2))
            assert last.bottom()<agenda_page.rows.viewport().height(),(last,agenda_page.rows.viewport().size())
            assert window.grab().save(str(output/'agenda-small.png'))
            window.resize(window.width(),original_height);app.processEvents()
            progress=dict(cfg['clock_appearance']['progress'])
            progress['countdowns']=[dict(id='fixtureCountdown',title='发布倒数日',date=day.toString('yyyy-MM-dd'),time='14:00',repeat='once')]
            assert runtime.clock.save(clock_appearance=dict(cfg['clock_appearance'],progress=progress))
            assert 'countdown' in agenda_page.calendar.markers[day.toPyDate()] and agenda_page.rows.count()==5
            from calendar_markers import month_markers,countdowns
            marks=month_markers(service.calendar_entries(),countdowns(cfg),day.toPyDate(),2)
            assert marks[day.toPyDate()]==agenda_page.calendar.markers[day.toPyDate()]
            assert window.grab().save(str(output/'readme-agenda.png'))
            cfg['resource_appearance']['theme']='dark';window.sync_window();app.processEvents()
            assert window.grab().save(str(output/'agenda-dark.png'))
            cfg['resource_appearance']['theme']='light';window.sync_window()
            window.resize(window.width(),original_height);app.processEvents()
            assert service.set_options(resource_alert_agenda=False)
            assert not agenda.timer.isActive() and not agenda.due() and not service.reminders()
            assert service.set_options(resource_compact_metrics=[*previous_metrics,'agenda'],
                                       resource_compact_pinned=['agenda',*previous_pins])
            assert service.fold(True);app.processEvents()
            assert agenda.timer.isActive() and not agenda.due()
            view=plan(window,window.width())
            item=next(row for row in view['routine_badges'] if row[0]=='agenda')
            assert '项目周会' in item[1]
            window.grab()
            point=window.reminder_bounds[window.reminder_kinds.index('agenda')].center()
            window.expand_from(point)
            assert not service.compact and window.page_key=='agenda'
            assert service.set_options(resource_compact_metrics=previous_metrics,resource_compact_pinned=previous_pins)
            assert service.set_options(resource_alert_agenda=True)
            agenda.announced.clear()
            with patch.object(runtime.dock,'preview',False),patch.object(runtime.tray,'showMessage') as notify,patch.object(service,'play_reminder_sound') as sound:
                agenda.sync();agenda.sync()
                notify.assert_called_once()
                sound.assert_called_once_with('agenda')
            assert service.fold(True)
            assert 'battery' in service.active_keys() and 'system_status' not in service.active_keys()
            with patch.object(runtime.dock,'preview',False),patch.object(runtime.tray,'showMessage') as notify,patch.object(service,'play_reminder_sound') as sound:
                for _ in range(2):service.accept_sample(dict(time=time.monotonic(),battery=(12,'battery')))
                notify.assert_called_once()
                sound.assert_called_once_with('battery')
            assert service.reminders()==(('agenda','项目周会'),('battery','12%'))
            app.processEvents();window.grab()
            assert window.reminder_kinds==['agenda','battery']
            assert window.grab().save(str(output/'readme-agenda-compact.png'))
            window.expand_from(window.reminder_bounds[0].center())
            assert window.page_key=='agenda' and not service.compact
            agenda_page.reminder.click();assert not agenda.due() and api.load_config()['resource_agenda_events'][0]['ack']
            assert agenda_page.reminder.text()=='恢复提醒'
            with patch.object(runtime.dock,'preview',False),patch.object(runtime.tray,'showMessage') as notify,patch.object(service,'play_reminder_sound') as sound:
                agenda_page.reminder.click();agenda.sync()
                notify.assert_called_once()
                sound.assert_called_once_with('agenda')
            assert agenda.due() and not api.load_config()['resource_agenda_events'][0]['ack']
            long_title='项目周会与跨部门供应链协同进度跟踪及验收工作安排、设备联调和交付问题复盘'
            assert agenda.update_event(agenda.due()[0]['id'],title=long_title)
            assert service.set_options(resource_halo=False,motion_enabled=True)
            assert service.fold(True);app.processEvents()
            assert window.marquee_title==long_title and window.animation.isActive()
            assert 37<=plan(window,window.width())['active_badges'][0][2]<=window.width()*.20
            frame=window.grab().toImage()
            window.marquee_since-=2
            assert frame!=window.grab().toImage()
            window.marquee_since=time.monotonic()
            assert window.grab().save(str(output/'readme-agenda-marquee.png'))
            assert service.set_options(motion_enabled=False)
            assert not window.animation.isActive()
            options=ResourceOptions(service);options.tabs.setCurrentIndex(2)
            for key in ('resource_alert_agenda','resource_alert_focus','resource_alert_water','resource_alert_battery'):
                assert options.fields[key].isChecked();options.fields[key].setChecked(False)
            assert options.commit() and not service.reminders() and 'battery' not in service.active_keys()
            options.deleteLater()
            checks.append('Compact status icons, full date/time format, shared routine badges, scrolling agenda title and cancel/restore. Countdown and agenda markers share one projection for both calendars.')
    finally:
        cfg['resource_enabled']=False;service.sync()
        if model:
            model.timer.stop();model.deleteLater()
        if agenda:
            agenda.timer.stop();agenda.deleteLater()
        service.pomodoro=previous_model
        service.agenda=previous_agenda
        cfg.clear();cfg.update(before);service.sync();api.save_config(cfg);app.processEvents()
    checks.append('Computer status shares the sampler, shows charge/low/muted/missing states and aligns the top and bottom edges of both dashboard rows.')
    checks.append('Pomodoro and hydration align their icons and readouts, persist, notify once and open from the capsule; device status, timers and the next agenda entry can stay visible with alerts disabled.')
    checks.append('The native add-event form receives a mouse click at the visible Save button; reminders and local records persist.')
    checks.append('Settings expose three QR entry points and cancellable download progress; the agenda paints per-source dates and rows in both themes, with deduplicated manual import.')
