"""Focused desktop feature checks and README captures on a private desktop."""
import copy
import datetime as dt
import json
import os
import statistics
import sys
import tempfile
import time
import traceback
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/name) for name in ('app','tests','tools')]


def run(output,checks):
    from run_isolated_test import assert_isolated
    assert_isolated()
    import dock as api
    from PyQt5.QtCore import QDate,QEvent,QPoint,QPointF,QRectF,Qt,QProcess
    from PyQt5.QtGui import QColor,QFont,QImage,QLinearGradient,QMouseEvent,QPainter,QPixmap
    from PyQt5.QtWidgets import QApplication,QInputDialog
    from runtime_controller import RuntimeController
    from ui_style import apply_theme,shutdown_ui
    from resource_memory_runner import sample
    from deck_runtime import installed_runtime
    from resource_deck import start_headless

    app=QApplication([]);app.setQuitOnLastWindowClosed(False);apply_theme(app,True)
    def pump(seconds=.08):
        until=time.monotonic()+seconds
        while time.monotonic()<until:app.processEvents();time.sleep(.010)
    def memory():
        values=[]
        for _ in range(5):
            pump(.16)
            values.append(sample(os.getpid())['private_working_set_mib'])
        return statistics.median(values)
    def grab(widget,name):
        pump()
        assert widget.grab().save(str(output/(name+'.png')))

    with tempfile.TemporaryDirectory(prefix='fishdock-widgets-') as folder:
        api.CONFIG_DIR=folder;api.CONFIG_PATH=str(Path(folder)/'config.json');api.LOG_PATH=str(Path(folder)/'dock.log')
        cfg=api.normalize_features(copy.deepcopy(api.DEFAULT_CONFIG))
        cfg.update(items=[],hide_tray=True,desktop_auto_sort=False,desktop_icon_mode='both',screen_corners=False,
                   panel_enabled=False,notes_enabled=False,flash_enabled=False,dock_visible=False,clock_enabled=False,
                   calendar_enabled=False,resource_enabled=False,resource_taskbar=False,resource_ai_tray=False,
                   resource_bt_tray=False,check_updates_on_start=False,autostart=False,card_scale=70)
        dock=api.Dock(cfg,preview=True);tray=api.DockTray(dock);dock.tray=tray
        runtime=tray.runtime=RuntimeController(dock,tray,api)
        try:
            baseline=memory()
            from custom_card_editor import CardEditor
            from custom_card_data import TEMPLATE,developer_prompt,parse_card_json,validate_card
            manager=runtime.custom_card_manager()
            draft=dict(TEMPLATE,title='今日看板',rows=[dict(kind='text',label='计划',value='检查本周进度'),
                       dict(kind='time',label='本机时间'),dict(kind='cpu',label='CPU'),dict(kind='memory',label='内存')])
            card_id='widgetfixture'
            assert manager.save([dict(validate_card(draft),id=card_id,layout={},visible=True,locked=False)])
            visible_memory=memory()
            assert manager.change(card_id,visible=False)
            editor=CardEditor(manager,card_id);editor.show();pump()
            assert 'countdown' in developer_prompt() and '导入 JSON' in developer_prompt()
            with patch.object(QInputDialog,'getMultiLineText',return_value=(json.dumps(draft,ensure_ascii=False),True)):
                editor.import_json()
            editor_memory=memory()
            assert editor.commit() and len(manager.windows)==1
            card_id=editor.identity
            editor.close();editor.deleteLater();pump(.3)
            card=manager.windows[card_id]
            assert runtime.resources.active_keys()=={'cpu','memory'}
            runtime.resources.latest.update(cpu=12,memory=(46,0,0));card.update()
            grab(card,'readme-custom-card')
            assert manager.change(card_id,visible=False) and not manager.windows and not runtime.resources.active_keys()
            assert api.load_config()['custom_cards'][0]['rows'][0]['value']=='检查本周进度'
            (output/'card-memory.json').write_text(json.dumps(dict(baseline=baseline,editor=editor_memory,one_card=visible_memory,
                scope='same isolated source process, five private working-set samples per stage, preview/supplied metrics'),indent=2),encoding='utf-8')
            checks.append('Native card editor: JSON import, saved desktop instance, shared metric demand, hide and reload.')

            art=QImage(240,160,QImage.Format_RGB32);art.fill(QColor('#96c3dd'))
            brush=QPainter(art);brush.setRenderHint(QPainter.Antialiasing);brush.setPen(Qt.NoPen)
            brush.setBrush(QColor('#ffe7bb'));brush.drawEllipse(QPoint(159,54),31,31)
            brush.setBrush(QColor('#4a88ad'));brush.drawEllipse(-30,98,300,130);brush.end()
            art_path=Path(folder)/'card-cover.png';assert art.save(str(art_path))
            quote_path=Path(folder)/'quote.json';quote_path.write_text(json.dumps({'quote':'把大目标拆小。\n今天先迈一步。'},ensure_ascii=False),encoding='utf-8')
            quote=validate_card(dict(title='每日一言',style='solid',width=395,header_date=True,arrangement='image_right',
                    colors=dict(surface='#edf5f9',text='#193747'),fonts=dict(title=21,body=18),
                    image=dict(path=str(art_path),height=104,fit='contain'),data_file=str(quote_path),rows=[dict(kind='data',label='',value='quote')]))
            quote_id='quotefixt'
            assert manager.save([dict(quote,id=quote_id,layout={},visible=True,locked=False)])
            quote_window=manager.windows[quote_id]
            assert not quote_window.image.isNull() and quote_window.row_boxes[0][1].right()<quote_window.photo_rect.left()
            assert quote_window.data['quote'].endswith('先迈一步。') and quote_window.card['fonts']['body']==18
            grab(quote_window,'readme-custom-card-designed')
            edited=CardEditor(manager,quote_id)
            assert edited.image.text()==str(art_path) and edited.header_date.isChecked() and edited.arrangement.currentData()=='image_right'
            assert edited.values()['fonts']['body']==18
            pasted=json.dumps(dict(quote,rows=[dict(kind='text',label='',value='第一行\n第二行')]),ensure_ascii=False)
            for file in (art_path,quote_path):
                pasted=pasted.replace(json.dumps(str(file),ensure_ascii=False),'"'+str(file)+'"')
            with patch.object(QInputDialog,'getMultiLineText',return_value=(pasted,True)):
                edited.import_json()
            assert edited.values()['image']['path']==str(art_path) and edited.values()['data_file']==str(quote_path)
            assert edited.values()['rows'][0]['value']=='第一行\n第二行'
            escaped=r'{"title":"每日一言","image":{"path":"D:\\图片\\鱼.png"},"rows":[]}'
            assert parse_card_json(escaped)['image']['path']==r'D:\图片\鱼.png'
            path_with_control_escapes=r'{"title":"每日一言","image":{"path":"D:\notes\test.png"},"rows":[]}'
            assert parse_card_json(path_with_control_escapes)['image']['path']==r'D:\notes\test.png'
            with patch.object(QInputDialog,'getMultiLineText',return_value=('{\n"title":',True)):
                edited.import_json()
            assert '第 2 行' in edited.status.text() and edited.values()['image']['path']==str(art_path)
            edited.close();edited.deleteLater()

            def fixture_card(tool,rows=()):
                card=validate_card(dict(title='自定义工具',tool=tool,rows=list(rows),width=340))
                assert manager.save([dict(card,id='toolfixture',visible=True,locked=False,layout={})])
                return manager.windows['toolfixture']
            from custom_card_tools import currency_rates,history_events
            search=fixture_card(dict(kind='search',url='https://zh.wikipedia.org/w/index.php?search={query}')).tool_widget
            search.query.setText('测试 & 词')
            with patch('custom_card_tools.QDesktopServices.openUrl') as open_link:
                search.submit();assert '%26' in bytes(open_link.call_args.args[0].toEncoded()).decode()
            timer=fixture_card(dict(kind='pomodoro',minutes=1,break_minutes=2)).tool_widget
            timer.start_or_pause();assert timer.timer.isActive()
            timer.deadline=time.monotonic()-1;timer.refresh();assert timer.resting and timer.remaining==120 and not timer.timer.isActive()
            history=history_events(dt.date.today(),'zh',lambda _,__:b'{"selected":[{"year":1950,"text":"Event"}]}')
            rates=currency_rates(lambda _,__:b'[{"date":"2026-11-06","quote":"USD","rate":1.25},{"date":"2026-11-06","quote":"CNY","rate":8}]')
            history_card=fixture_card(dict(kind='history',lang='zh',limit=2))
            manager.feeds.cache[('history','zh')]=dt.date.today(),history;manager.feeds.changed.emit()
            assert '1950' in history_card.tool_widget.entries[0].text()
            rate_card=fixture_card(dict(kind='rates',amount=100))
            manager.feeds.cache[('rates','')]=dt.date.today(),rates;manager.feeds.changed.emit()
            assert rate_card.tool_widget.result.text()=='640.00 CNY'
            conversion=fixture_card(dict(kind='convert',units=[dict(name='千米',factor=1000),dict(name='米',factor=1)])).tool_widget
            assert conversion.result.text()=='1,000 米'
            remote=fixture_card(dict(kind='feed',url='https://example.org/today/{date}.json'),[dict(kind='remote',label='',value='items.0.title')])
            manager.feeds.cache[remote.feed_key]=dt.date.today(),dict(data={'items':[{'title':'自定义在线内容'}]});manager.feeds.changed.emit()
            from custom_cards import card_value
            assert card_value(remote.card['rows'][0],{},dt.datetime.now(),remote=remote.remote)=='自定义在线内容'
            assert manager.save([])
            checks.append('Native cards import Explorer paths and escaped JSON without altering text line breaks, preserve values on invalid input, and support local/HTTPS bindings and native tools.')

            from feature_config import SPECTRUM_STYLES
            assert runtime.set_spectrum_options(spectrum_enabled=True,theme_color='#54b2de')
            assert cfg['spectrum_color_mode']=='colorful'
            spectrum=runtime.spectrum
            bridge=runtime.resources.deck
            assert bridge.signature[6] and not bridge.signature[2]
            from math import sin
            frame=[.10+.83*abs(sin(i*.47)*sin(i*.12+.45)) for i in range(120)]
            bridge.accept(dict(type='spectrum',levels=frame))
            assert len(spectrum.levels)==120
            collage=QImage(680,390,QImage.Format_RGB32);collage.fill(QColor('#142636'))
            painter=QPainter(collage)
            for i,(title,style) in enumerate(SPECTRUM_STYLES):
                assert runtime.set_spectrum_options(spectrum_style=style)
                pump()
                image=spectrum.grab().toImage().convertToFormat(QImage.Format_ARGB32)
                assert image.pixelColor(0,0).alpha()==0 and image.pixelColor(image.width()-1,0).alpha()==0
                if style=='ring':assert image.pixelColor(image.width()//2,image.height()//2).alpha()==0
                assert any(image.pixelColor(x,y).alpha()>160 for x in range(4,image.width()-4,2) for y in range(4,image.height()-4,2))
                x,y=((18,14),(354,14),(18,122),(354,122),(354,240))[i]
                painter.setPen(QColor('#e4edf4'));font=QFont('Microsoft YaHei UI');font.setPixelSize(15);painter.setFont(font)
                painter.drawText(QRectF(x,y,300,23),Qt.AlignLeft|Qt.AlignVCenter,title)
                painter.drawImage(x+max(0,(288-image.width())//2),y+24,image)
            painter.end();assert collage.save(str(output/'readme-desktop-spectrum.png'))
            colorful=spectrum.grab().toImage()
            assert runtime.set_spectrum_options(spectrum_color_mode='mono')
            assert colorful!=spectrum.grab().toImage()
            start=spectrum.pos();center=spectrum.rect().center();glob=spectrum.mapToGlobal(center);shift=QPoint(-72,-41)
            for kind,button,buttons,point in ((QEvent.MouseButtonPress,Qt.LeftButton,Qt.LeftButton,glob),
                    (QEvent.MouseMove,Qt.NoButton,Qt.LeftButton,glob+shift),
                    (QEvent.MouseButtonRelease,Qt.LeftButton,Qt.NoButton,glob+shift)):
                QApplication.sendEvent(spectrum,QMouseEvent(kind,QPointF(center),QPointF(point),button,buttons,Qt.NoModifier))
            assert spectrum.pos()!=start and cfg['spectrum_layout']
            spectrum.move(spectrum.pos()-QPoint(120,80));before=spectrum.size()
            grip=spectrum.grip_rect().center();origin=spectrum.mapToGlobal(grip);delta=QPoint(58,31)
            for kind,button,buttons,point in ((QEvent.MouseButtonPress,Qt.LeftButton,Qt.LeftButton,origin),
                    (QEvent.MouseMove,Qt.NoButton,Qt.LeftButton,origin+delta),
                    (QEvent.MouseButtonRelease,Qt.LeftButton,Qt.NoButton,origin+delta)):
                QApplication.sendEvent(spectrum,QMouseEvent(kind,QPointF(grip),QPointF(point),button,buttons,Qt.NoModifier))
            assert cfg['spectrum_manual_size'] and spectrum.width()==before.width()+58 and spectrum.height()==before.height()+31
            size=spectrum.size()
            assert runtime.set_spectrum_options(spectrum_style='line',spectrum_color_mode='mono',spectrum_mono_color='#ffbbaa')
            assert spectrum.size()==size and cfg['spectrum_mono_color']=='#ffbbaa'
            assert runtime.set_spectrum_options(spectrum_enabled=False) and runtime.resources.deck is None
            checks.append('Five native spectrum renderers preserve transparent pixels, save a real drag and only demand the bridge while enabled.')

            from clock_progress import ClockProgressDialog
            from clock_faces import countdown_date,orbit_items
            from settings_effects import save_changes
            clock=runtime.clock
            assert clock.option('appearance')['progress']['primary']=='work'
            def save(progress):
                return save_changes(tray,api,dict(clock_enabled=True,clock_style='orbit',
                    clock_appearance=dict(clock.option('appearance'),progress=progress)))
            edit=ClockProgressDialog(dock,clock.option('appearance')['progress'],save)
            edit.add_countdown('发薪日','monthly');identity=list(edit.rows)[-1]
            role,(_,target,_)=edit.rows[identity]
            target.setDate(QDate(2026,1,31));role.setCurrentIndex(role.findData('main'))
            edit.add_countdown('生日','yearly');birthday=list(edit.rows)[-1]
            edit.rows[birthday][1][1].setDate(QDate(2024,2,29))
            edit.commit()
            progress=clock.option('appearance')['progress']
            assert progress['primary']==identity and progress['secondary']==['week','month','year',birthday]
            pay,birth=progress['countdowns']
            assert countdown_date(pay,dt.date(2026,2,8))==dt.date(2026,2,28)
            assert countdown_date(birth,dt.date(2027,2,8))==dt.date(2027,2,28)
            assert orbit_items(dt.datetime(2026,2,8),clock.option('appearance'))[0][identity][1]=='20 天'
            from clock_faces import countdown_display,countdown_window
            anchor=dict(date='2026-01-31',time='09:15',repeat='monthly')
            moment=dt.datetime(2026,2,28,8,58)
            previous,due=countdown_window(anchor,moment)
            assert previous==dt.datetime(2026,1,31,9,15) and due==dt.datetime(2026,2,28,9,15)
            assert countdown_display(anchor,moment)[0]=='17 分' and .99<countdown_display(anchor,moment)[2]<1
            assert countdown_display(dict(anchor,repeat='once'),moment)[2] is None
            clock.resize(440,190);grab(clock,'readme-clock-countdown')
            checks.append('Clock editor: selecting a primary demotes the prior one, secondary items persist, monthly and leap-day recurrence verified.')
            from desktop_clock import draw_clock
            from clock_options import ClockOptions
            clock_editor=ClockOptions(clock)
            clock_editor.fields['text_color'].setText('#2277cc')
            assert not clock_editor.fields['auto_contrast'].isChecked()
            clock_editor.fields['auto_contrast'].setChecked(True)
            assert not clock_editor.fields['text_color'].text()
            clock_editor.deleteLater()
            for style,name in (('digital','readme-clock-digital'),('calendar','readme-clock-week')):
                clock_image=QImage(440,190,QImage.Format_ARGB32_Premultiplied);clock_image.fill(Qt.transparent)
                painter=QPainter(clock_image);audit=[]
                options=dict(clock.option('appearance'),theme='dark',material='solid',color='#172733',opacity=100,accent_color='#ffb580',
                             _now=dt.datetime(2026,10,1,12,10,56),_text_audit=audit,auto_contrast=True)
                draw_clock(painter,QRectF(0,0,440,190),dock,options,style);painter.end()
                assert clock_image.save(str(output/(name+'.png')))
                words={value for value,*_ in audit}
                if style=='digital':
                    assert {'12:10','56','0','6','12','18','24'}<=words
                else:
                    assert '国庆节' in words and any('发薪日' in value for value in words)
            checks.append('Clock faces: second readout and 24-hour ruler, holiday/lunar week and countdown, manual text entry switches off auto color.')

            from resource_weather import air_quality,forecast,moon_phase,weather_time
            from urllib.parse import urlsplit,parse_qs
            dates=[dt.date(2026,11,7)+dt.timedelta(days=i) for i in range(8)]
            def forecast_data(url):
                fields=parse_qs(urlsplit(url).query)
                assert 'daylight_duration' in fields['daily'][0] and fields['hourly']==['temperature_2m'] and fields['timezone']==['auto']
                return dict(utc_offset_seconds=28800,current=dict(temperature_2m=13,weather_code=2,time='2026-11-08T13:15',
                            apparent_temperature=12,relative_humidity_2m=62,wind_speed_10m=11),
                    hourly=dict(time=[f'2026-11-08T{i}:00' for i in range(13,20)],temperature_2m=[13,14,15,15,14,12,11]),
                    daily=dict(time=[str(day) for day in dates],temperature_2m_max=[14,15,16,12,14,16,14,13],
                        temperature_2m_min=[7,8,9,6,4,6,7,5],weather_code=[2,2,61,3,0,0,3,2],
                        precipitation_probability_max=[12,10,90,23,4,6,12,21],sunrise=[f'{day}T06:45' for day in dates],
                        sunset=[f'{day}T17:09' for day in dates],daylight_duration=[37440]*8))
            weather=forecast('天津',forecast_data)
            assert weather_time(weather).utcoffset()==dt.timedelta(hours=8)
            assert weather_time(dict(utc_offset_seconds=-18000)).utcoffset()==dt.timedelta(hours=-5)
            air=air_quality({'天津':(39.14,117.17),'沈阳':(41.79,123.43)},lambda _:[
                dict(current=dict(us_aqi=74,pm2_5=23,pm10=41,ozone=62)),
                dict(current=dict(us_aqi=19,pm2_5=0,pm10=12,ozone=28))])
            assert len(weather['hours'])==6 and weather['days'][1]['rain']==10 and air['沈阳']['pm2_5']==0
            from resource_weather import WeatherJob,qweather_air
            locations={'天津':(39.14,117.17),'沈阳':(41.79,123.43)}
            with patch('resource_weather.air_quality',side_effect=[{'天津':air['天津']},{'沈阳':dict(air['沈阳'],hourly=True)}]) as request_air:
                backed,_=WeatherJob(locations).read_air(locations)
                assert set(backed)==set(locations) and request_air.call_args.args[0]=={'沈阳':locations['沈阳']}
            report=qweather_air(locations['天津'],'demo.qweatherapi.com','key',lambda _,__:dict(
                indexes=[dict(code='cn-mee',aqi=45)],pollutants=[dict(code='o3',concentration=dict(value=15.5,unit='ppb'))]))
            assert report['scale']=='中国 AQI' and report['pollutants']['ozone']==(15.5,'ppb')
            assert moon_phase('2000-01-07T02:14')==('新月',0)
            weather['air']=air['天津']
            service=runtime.resources
            assert service.set_options(resource_enabled=True,resource_auto_hide=False,resource_collapsed=False,
                resource_music=True,resource_ai=False,resource_lyrics=False,resource_weather=True,
                resource_weather_days=7,resource_weather_cities=['天津','沈阳'],resource_news=True,
                resource_expanded_width=560,resource_expanded_height=360)
            window=service.window
            service.extras.weather=[weather,dict(weather,name='沈阳',air=air['沈阳'])]
            window.select_page('weather');pump()
            assert window.weather_view.cards.columns==2
            window.weather_view.city.setCurrentIndex(1)
            assert window.weather_view.cards.city_index==1
            window.weather_view.city.setCurrentIndex(0)
            cards=window.weather_view.cards
            assert cards.sun_clock.isActive()
            def card_colors(hour,minute,shot_name=''):
                moment=dt.datetime(2026,11,8,hour,minute,tzinfo=dt.timezone(dt.timedelta(hours=8)))
                with patch('resource_extras_view.weather_time',return_value=moment):
                    if shot_name:grab(window,shot_name)
                    shot=cards.grab()
                ratio=shot.devicePixelRatioF()
                pixels=shot.toImage()
                x=(cards.width()+cards.gap)/2
                y=cards.card_height+cards.gap
                return tuple(pixels.pixelColor(round((left+4)*ratio),round((top+24)*ratio)).name()
                             for left,top in ((0,0),(x,0),(0,y),(x,y)))
            tones=[card_colors(hour,minute,'readme-weather-detail' if hour==17 else '')
                   for hour,minute in ((6,45),(13,15),(17,9),(23,0))]
            assert all(len(set(row))==4 for row in tones),tones
            assert len({row[:3] for row in tones})==1 and len({row[3] for row in tones})==4,tones
            assert card_colors(16,50)[3]!=card_colors(17,9)[3]
            from resource_options import background
            from PyQt5.QtTest import QTest
            from settings_interaction_tests import wheel
            weather_page=window.view('weather')
            cards=weather_page.content.cards
            width=cards.width()
            assert weather_page.verticalScrollBar().maximum()==0
            service.set_options(resource_expanded_height=180);pump()
            scrollbar=weather_page.verticalScrollBar()
            assert scrollbar.maximum()>0 and not scrollbar.isVisible() and cards.width()==width
            app.setActiveWindow(window);weather_page.setFocus()
            wheel(weather_page.viewport(),-120)
            assert scrollbar.value()>0 and cards.width()==width
            scrollbar.setValue(0)
            wheel(weather_page.viewport(),0,pixels=-23)
            assert scrollbar.value()==23
            window.select_page('music');pump()
            assert not cards.sun_clock.isActive()
            assert window.music_view.verticalScrollBar().value()==0
            window.select_page('weather');pump()
            assert scrollbar.value()==0
            QTest.keyClick(weather_page,Qt.Key_PageDown);assert scrollbar.value()>0
            service.set_options(resource_expanded_height=360);pump()
            assert scrollbar.value()==0 and cards.width()==width
            checks.append('Hidden capsule scrollbars preserve card widths, mouse and keyboard scrolling, and start each selected page at its own top.')
            original_style=window.styleSheet()
            dark=dict(background(cfg),theme='dark')
            assert service.set_options(resource_background='custom',resource_appearance=dark)
            pump()
            assert service.window is window and not window.colors['light'] and window.styleSheet()==original_style
            QTest.mouseClick(window.page_buttons['music'],Qt.LeftButton)
            assert window.page_key=='music'
            QTest.mouseClick(window.page_buttons['weather'],Qt.LeftButton)
            assert window.page_key=='weather'
            assert len(set(card_colors(23,0,'weather-dark')))==4
            for theme in ('light','dark'):
                clear=dict(background(cfg),material='clear',theme=theme,opacity=18)
                assert service.set_options(resource_background='custom',resource_appearance=clear)
                pump()
                shot=window.grab();pixels=shot.toImage();scale=shot.devicePixelRatioF()
                def alpha_at(widget,x):
                    point=widget.mapTo(window,QPoint(x,widget.height()//2))
                    return pixels.pixelColor(round(point.x()*scale),round(point.y()*scale)).alpha()
                city=window.weather_view.city;tab=window.page_buttons['weather'];week=window.weather_view.week
                alphas=(alpha_at(city,city.width()//2),alpha_at(tab,5),alpha_at(week,4))
                assert all(0<a<128 for a in alphas), (theme,alphas)
                assert city.width()<=144 and city.height()==week.height()==22
                assert shot.save(str(output/('weather-clear-'+theme+'.png')))
                QTest.mouseClick(city,Qt.LeftButton);pump()
                assert city.view().isVisible()
                QTest.keyClick(city.view(),Qt.Key_Escape)
                assert not city.view().isVisible()
            checks.append('Clear material keeps weather controls and selected tabs translucent and clickable in light and dark.')
            assert service.set_options(resource_background='global')
            service.set_options(resource_expanded_width=260,resource_expanded_height=180)
            pump();assert window.weather_view.cards.columns==1
            grab(window,'weather-narrow')
            service.set_options(resource_expanded_width=520,resource_expanded_height=180)
            checks.append('Four independent weather surfaces in light and dark; city-local dawn/day/dusk/night transitions, visible-only clock, forecast/AQI readings and two/one column layouts.')

            image=QImage(640,360,QImage.Format_RGB32)
            painter=QPainter(image)
            gradient=QLinearGradient(0,0,0,360)
            gradient.setColorAt(0,QColor('#8bbfc9'));gradient.setColorAt(.7,QColor('#e7cd98'));gradient.setColorAt(1,QColor('#24667e'))
            painter.fillRect(image.rect(),gradient)
            painter.setPen(Qt.NoPen);painter.setBrush(QColor('#fef3cc'));painter.drawEllipse(QPoint(470,115),34,34)
            from PyQt5.QtGui import QPolygonF
            for color,points in (('#4d7d87',[(0,252),(130,174),(206,225),(320,160),(477,231),(640,200)]),
                                 ('#305469',[(0,300),(180,242),(300,278),(442,224),(640,262)])):
                painter.setBrush(QColor(color));painter.drawPolygon(QPolygonF([QPointF(x,y) for x,y in [*points,(640,360),(0,360)]]))
            painter.end()
            bridge=service.deck
            bridge.media=dict(track=dict(id='demo',title='海岸线的午后',artist='测试音轨',duration=214,position=77,state='Playing',
                canToggle=True,canNext=True,canPrevious=True,canSeek=True),tracks=[dict(id='demo',title='海岸线的午后',source='示例播放器')])
            bridge.cover=QPixmap.fromImage(image);bridge.levels=frame[:8];bridge.status=''
            window.select_page('music');pump()
            media=window.music_view
            assert media.cover.geometry().right()<media.title.geometry().left() and media.slider.isEnabled()
            assert media.card.isAncestorOf(media.cover) and media.card.isAncestorOf(media.buttons['PlayPause'])
            grab(window,'readme-media-compact')
            service.set_options(resource_expanded_width=260)
            pump()
            assert media.card.width()<=media.viewport().width() and media.cover.width()==42
            assert media.horizontalScrollBar().maximum()==0
            service.set_options(resource_traffic=True)
            service.latest['traffic']=dict(day=(3*2**30,800*2**20),month=(30*2**30,8*2**30),year=(300*2**30,80*2**30))
            window.select_page('traffic');pump()
            assert window.traffic.summary.columns==1 and window.view('traffic').verticalScrollBar().maximum()>0
            service.set_options(resource_expanded_width=520,resource_expanded_height=195);pump()
            assert window.traffic.summary.columns==3 and window.view('traffic').verticalScrollBar().maximum()==0
            grab(window,'readme-traffic-cards')
            checks.append('Media and traffic use native card surfaces, retain controls and period totals, and fit without horizontal scrolling at 260 pixels.')

            from content_sources import read_feed,read_bing
            rss='''<rss><channel><title>城市周报</title>
              <item><title>图书馆周末延长开放时间</title><link>https://example.org/library</link>
                <pubDate>Sun, 08 Nov 2026 02:30:00 GMT</pubDate></item>
              <item><title>滨海步道新增两处观景平台</title><link>https://example.org/coast</link>
                <pubDate>Sun, 08 Nov 2026 01:10:00 GMT</pubDate></item>
              <item><title>Unsafe</title><link>file:///C:/test</link></item></channel></rss>'''
            rows=read_feed(rss.encode(),'https://example.org/rss')
            assert len(rows)==2
            atom=read_feed('<feed xmlns="http://www.w3.org/2005/Atom"><title>城市天气</title><entry><title>下周早晚温差加大，出门请加衣</title><link href="/note"/><updated>2026-11-08T00:00:00Z</updated></entry></feed>'.encode(),'https://example.org/feed')
            assert atom[0]['url']=='https://example.org/note' and atom[0]['stamp']
            window.select_page('news');news=window.view('news').content
            service.set_options(resource_expanded_height=215)
            news.set_headlines(rows+atom);news.status.clear()
            with patch('resource_content.QDesktopServices.openUrl') as open_url:
                news.rows.itemAt(0).widget().click()
                assert open_url.call_args.args[0].toString()=='https://example.org/library'
            grab(window,'readme-news')

            from resource_redesign_tests import fixtures
            from resource_statistics import text as draw_stat
            sample_provider=fixtures()[0]
            summary=sample_provider['days'][0]['summary']
            summary.update(cost=10.37,unpriced=2)
            day=dt.date.today().isoformat()
            sample_provider['hours']=[dict(date=f'{day}T{hour:02}',summary=dict(summary,cost=value))
                                      for hour,value in ((2,2.17),(8,1.20),(13,3.80),(19,3.20))]
            service.set_options(resource_ai=True,resource_expanded_width=560,resource_expanded_height=440)
            bridge.accept(dict(type='ai',providers=[sample_provider]))
            window.select_page('ai');pump()
            stats=window.ai_view.statistics
            painted_labels=set()
            def record_ai_text(painter,rect,value,*args):
                painted_labels.add(value)
                draw_stat(painter,rect,value,*args)
            with patch('resource_statistics.text',record_ai_text):
                grab(window,'readme-ai-cost')
            labels=painted_labels.copy()
            assert {'10.37','$10.37','USD','含估算 · 2 条未定价'}<=labels and not stats.provider.isVisible()
            from resource_ai_tray import AiPopup
            ai_popup=AiPopup(service);ai_popup.resize(520,432);ai_popup.show()
            painted_labels.clear()
            with patch('resource_statistics.text',record_ai_text):
                grab(ai_popup,'ai-tray-cost')
            assert labels<=painted_labels
            ai_popup.close();ai_popup.deleteLater()
            checks.append('AI cost: capsule and tray render clean currency, source totals and a number-only donut, with pricing status below the amount.')

            samples={'images':[dict(title='海岸日光（演示图）',copyright='内置测试画面',copyrightlink='/search?q=sample',urlbase='/th?id=OHR.Sample',startdate='20261108')]*8}
            pictures=read_bing(json.dumps(samples).encode())
            assert len(pictures)==8 and pictures[0]['picture'].startswith('https://www.bing.com/')
            assert not window.page_enabled('picture')
            assert runtime.set_daily_picture_options(daily_picture_enabled=True)
            daily_card=runtime.daily_picture;daily=daily_card.content
            daily.items=pictures;daily.set_picture(image);daily.update_controls()
            assert daily.previous.isEnabled() and daily.story.isEnabled()
            service.set_options(resource_enabled=False)
            assert daily_card.isVisible() and daily_card.isWindow() and runtime.daily_picture is daily_card
            grab(daily_card,'readme-daily-picture')
            assert daily.photo.geometry().bottom()<daily.title.geometry().top()
            assert daily.download.isEnabled() and daily.wallpaper.isEnabled()
            actions=(daily.reload,daily.story,daily.download,daily.wallpaper)
            assert all(not button.text() and not button.icon().isNull() and button.toolTip() for button in actions)
            assert all(button.geometry().bottom()<daily.photo.y() for button in actions)
            assert len({button.y() for button in actions})==1 and daily.status.isHidden()
            tight_height=daily_card.height()
            assert tight_height-daily.photo.height()<88
            with patch('resource_content.QDesktopServices.openUrl') as open_story:
                daily.story.click();assert open_story.call_args.args[0].toString()==pictures[0]['story']
            daily.set_status('已保存原图');pump();assert daily.status.isVisible() and daily_card.height()>tight_height
            daily.set_status('');pump();assert daily_card.height()==tight_height
            assert runtime.set_daily_picture_options(daily_picture_material='solid',daily_picture_color='#82a9c9')
            assert daily_card.appearance['material']=='solid' and daily_card.appearance['color']=='#82a9c9'
            gallery=Path(folder)/'gallery';gallery.mkdir()
            assert art.save(str(gallery/'a.png')) and image.save(str(gallery/'b.jpg'))
            from content_sources import download_bing_original
            from io import BytesIO
            from threading import Event
            original=(gallery/'b.jpg').read_bytes();destination=Path(folder)/'downloaded.jpg'
            class BingResponse(BytesIO):
                headers={'Content-Length':str(len(original))}
                def geturl(self):return pictures[0]['original']
            with patch('urllib.request.urlopen',return_value=BingResponse(original)):
                assert download_bing_original(pictures[0]['original'],destination,Event()) and destination.read_bytes()==original
            with patch('urllib.request.urlopen',return_value=BingResponse(b'invalid')):
                try:download_bing_original(pictures[0]['original'],destination,Event())
                except ValueError:pass
                else:raise AssertionError('Invalid download replaced the file')
            assert destination.read_bytes()==original
            assert runtime.set_daily_picture_options(daily_picture_source='local',daily_picture_local_paths=[str(gallery)],daily_picture_interval=5)
            until=time.monotonic()+3
            while daily.job and time.monotonic()<until:pump(.03)
            assert [item['title'] for item in daily.items]==['a','b'] and daily.timer.interval()==5000
            daily.tick()
            while daily.job and time.monotonic()<until:pump(.03)
            assert daily.index==1 and not daily.photo.image.isNull()
            daily.tick()
            while daily.job and time.monotonic()<until:pump(.03)
            assert daily.index==0
            with patch.object(dock,'preview',False),patch.object(dock,'start_backdrop'),patch('wallpaper_source.set_wallpaper') as apply_wallpaper:
                daily.wallpaper.click()
                finish=time.monotonic()+2
                while daily.job and time.monotonic()<finish:pump(.03)
                apply_wallpaper.assert_called_once_with((gallery/'a.png').resolve())
                assert daily.status.text()=='已设为桌面壁纸'
            from component_passthrough import set_component,set_mode
            from window_layers import native
            def passes(widget):return widget.testAttribute(Qt.WA_TransparentForMouseEvents) and bool(native().GetWindowLongW(int(widget.winId()),-20)&32)
            assert set_component(runtime,'picture',True) and passes(daily_card)
            assert set_mode(runtime,'none') and not passes(daily_card)
            assert set_mode(runtime,'all') and passes(daily_card)
            assert runtime.set_spectrum_options(spectrum_enabled=True) and passes(runtime.spectrum)
            assert set_mode(runtime,'custom') and passes(daily_card) and not passes(runtime.spectrum)
            assert set_component(runtime,'picture',False) and not passes(daily_card)
            assert runtime.set_spectrum_options(spectrum_enabled=False)
            with patch('taskbar_menu.auto_hide',side_effect=(False,True)),patch.object(service,'settings') as open_settings:
                tray.rebuild();taskbar=next(action.menu() for action in tray.menu.actions() if action.text()=='任务栏')
                titles={action.text() for action in taskbar.actions()}
                assert {'任务栏效果','任务栏文字','自动隐藏 Windows 任务栏','任务栏监控设置…'}<=titles
                next(action for action in taskbar.actions() if action.text()=='任务栏监控设置…').trigger()
                open_settings.assert_called_once_with(page=1)
                hide=next(action for action in taskbar.actions() if action.text()=='自动隐藏 Windows 任务栏')
                with patch.object(dock,'preview',False):hide.trigger()
                assert hide.isChecked()
            checks.append('Daily picture has a compact icon toolbar with working actions, dynamic feedback height, material and local slideshow; per-window Win32 click-through and grouped taskbar menu.')
            checks.append('Media keeps cover, transport, seek and a spectrum. RSS/Atom row opens its URL. Daily picture stays visible with the resource capsule off.')

            from PyQt5.QtWidgets import QDialog,QVBoxLayout
            from ui_style import ModernComboBox
            popup_host=QDialog()
            popup_layout=QVBoxLayout(popup_host)
            combo=ModernComboBox();combo.setFixedWidth(106);combo.setMaxVisibleItems(5)
            combo.addItems(['短选项','不可选选项','长文字用于检查下拉框换行，完整内容需要保留。'*9,
                            *[f'选项 {i}' for i in range(12)]])
            combo.model().item(1).setEnabled(False)
            popup_layout.addWidget(combo);popup_host.show()
            for theme in ('light','dark'):
                apply_theme(app,theme=='light')
                app.setActiveWindow(popup_host);combo.setFocus()
                QTest.mouseClick(combo,Qt.LeftButton);pump()
                view=combo.view()
                assert view.isVisible() and view.window().width()>combo.width(), (
                    theme, view.isVisible(), combo.isVisible(), view.window().geometry(), combo.width(), app.activeWindow())
                assert view.sizeHintForRow(2)>3*view.fontMetrics().lineSpacing()
                assert view.window().screen().availableGeometry().contains(view.window().geometry())
                combo.choose_popup(combo.model().index(1,0))
                assert combo.currentIndex()==0 and view.isVisible()
                grab(view.window(),'dropdown-'+theme)
                QTest.keyClick(view,Qt.Key_Escape)
                assert not view.isVisible()
            popup_host.close();popup_host.deleteLater();apply_theme(app,True)
            checks.append('Shared dropdown widens to the screen, wraps long labels, skips disabled choices, scrolls and closes by keyboard in light and dark.')

            runtime.set_lite(True,persist=False)
            original_start=service.start_job
            def actual_rank_sampler():
                with patch.object(dock,'preview',False):original_start()
            started=time.monotonic()
            with patch.object(service,'start_job',actual_rank_sampler):
                assert service.set_options(resource_enabled=True,resource_open_page='resources',
                    resource_rank=True,resource_interval=5,resource_music=False,resource_ai=False,resource_weather=False)
            while time.monotonic()-started<2.5 and not service.latest.get('rank',{}).get('cpu'):
                pump(.03)
            first=time.monotonic()-started
            assert service.latest.get('rank',{}).get('cpu') and len(service.history)==1,(first,service.signature)
            rank_time=service.observed['rank']
            while time.monotonic()-rank_time<2 and service.observed['rank']==rank_time:pump(.03)
            assert service.observed['rank']>rank_time and len(service.history)==1
            interval=service.observed['rank']-rank_time
            service.window.select_page('news')
            assert 'rank' not in service.active_keys()
            (output/'rank-latency.json').write_text(json.dumps(dict(first_cpu_seconds=round(first,3),
                next_cpu_seconds=round(interval,3),ordinary_interval=5),indent=2),encoding='utf-8')
            checks.append('Real NT process readings: CPU rank warms and refreshes separately from the 5 s chart cycle, and stops on another page.')

            process=QProcess()
            import ctypes
            kernel=ctypes.windll.kernel32;before=kernel.GetErrorMode()
            helper=ROOT/'artifacts/deck-bridge/BigFishDeckBridge.exe'
            start_headless(process,helper,'--self-test',installed_runtime())
            assert kernel.GetErrorMode()==before
            assert process.waitForFinished(12000),bytes(process.readAllStandardError())
            receipt=json.loads(bytes(process.readAllStandardOutput()).decode('utf-8'))
            assert receipt['passed'] and receipt['workingSetLimit']==47*2**20 and receipt['processErrorMode']&3==3
            checks.append('Native Bridge child inherits silent error mode, its parent is restored, and Windows reports the enforced 47 MiB total working-set cap.')

            runtime.set_lite(False,persist=False)
            identity=runtime.notes.new()
            assert runtime.notes.update_and_save(identity,title='本周安排',text='确认图纸\n检查现场进度',
                html='<p>确认图纸</p><p>检查现场进度</p>')
            other=runtime.notes.new()
            assert runtime.notes.update_and_save(other,title='待采购',text='补充备件',html='<p>补充备件</p>')
            note=runtime.notes.windows[other]
            note.note_tabs.setCurrentIndex(0);pump()
            assert runtime.notes.windows[identity] is note and note.note_tabs.count()==2
            assert note.editor.toPlainText()=='确认图纸\n检查现场进度'
            assert runtime.notes.flush()
            grab(note,'readme-note-tabs')
            component_card=dict(validate_card(draft),id='componentcard',visible=True,locked=False,layout={})
            assert manager.save([component_card])
            assert service.set_options(resource_enabled=True,resource_collapsed=False,resource_ai=True,
                resource_music=True,resource_weather=True,resource_auto_hide=False,
                clock_enabled=True,calendar_enabled=True,daily_picture_enabled=True)
            from resource_settings import ResourceOptions
            from resource_options import DESKTOP_COMPONENTS,RESOURCE_PAGES
            options=ResourceOptions(service)
            options.tabs.setCurrentIndex(8)
            for key in (*DESKTOP_COMPONENTS,*RESOURCE_PAGES):
                field=options.location_fields[key]
                field.setCurrentIndex(field.findData('capsule' if key in DESKTOP_COMPONENTS else 'desktop'))
            order=['calendar','notes','custom','picture','clock']
            options.orders['resource_component_order']=order
            options.tabs.setCurrentIndex(0)
            assert options.commit()
            options.deleteLater();pump()
            assert set(service.desktop_cards)==set(RESOURCE_PAGES)
            assert service.deck.signature[0] and service.deck.signature[2]
            window=service.window
            assert all(not window.page_buttons[key].isVisible() for key in RESOURCE_PAGES)
            assert [window.page_buttons[key].x() for key in order]==sorted(window.page_buttons[key].x() for key in order)
            assert all(window.nav_content.rect().contains(button.geometry())
                       for button in window.page_buttons.values() if button.isVisible())
            for key in order:
                window.select_page(key);pump()
                hosted={'calendar':runtime.calendar,'clock':runtime.clock,'notes':runtime.notes.windows.get(identity),
                        'picture':runtime.daily_picture,'custom':manager.windows.get('componentcard')}[key]
                assert hosted is not None and hosted.isVisible() and not hosted.isWindow()
                assert hosted.parentWidget() is window.view(key).host
                if key=='notes':
                    assert hosted.editor.toPlainText()=='确认图纸\n检查现场进度' and hosted.collapse_button.isHidden()
                    assert hosted.note_tabs.count()==2
                if key=='custom':assert {'cpu','memory'}<=service.active_keys()
            service.set_options(resource_expanded_height=304)
            window.select_page('calendar');grab(window,'readme-capsule-components')
            assert service.fold(True)
            pump()
            assert not runtime.calendar.isVisible()
            assert all(card.isVisible() and not hasattr(card,'fold_button') for card in service.desktop_cards.values())
            assert service.set_options(resource_enabled=False)
            assert not service.window and all(card.isVisible() for card in service.desktop_cards.values())
            grab(service.detached('resources'),'detached-resources')
            assert service.set_options(resource_component_locations={'notes':'desktop'})
            pump()
            assert not service.desktop_cards and runtime.notes.windows[identity].isWindow()
            assert runtime.notes.windows[identity].collapse_button.isHidden()
            assert runtime.clock.isWindow() and runtime.calendar.isWindow() and runtime.daily_picture.isWindow()
            assert manager.windows['componentcard'].isWindow() and api.load_config()['resource_component_order'][:5]==order
            checks.append('Component location and tab order persist; embedded native views keep their controls, and detached resources survive folding and disabling the capsule.')

            from dependency_prompts import DependencyPrompts, NET_INSTALLER
            reminder=DependencyPrompts(runtime)
            with patch('dependency_prompts.installed_runtime',return_value=None),patch('dependency_prompts.installed_pawnio',return_value=''), \
                 patch('dependency_prompts.QDesktopServices.openUrl',return_value=True) as open_installer,patch('pawnio_setup.launch') as launch:
                reminder.request(True,True);pump()
                box=reminder.dialog
                assert box and '.NET 10' in box.text()
                next(button for button in box.buttons() if '下载' in button.text()).click();pump()
                assert open_installer.call_args.args[0].toString()==NET_INSTALLER
                box=reminder.dialog
                assert box and 'PawnIO' in box.text()
                next(button for button in box.buttons() if '安装' in button.text()).click();pump()
                launch.assert_called_once_with()
                again=DependencyPrompts(runtime)
                again.request(True,True);pump()
                assert again.dialog is None and again.seen=={'dotnet','pawnio'}
                again.close()
            reminder.close()
            checks.append('First-use missing dependency prompts offer native install actions and stay dismissed across a fresh session.')
            menu=tray.menu
            menu.popup(QPoint(12,12));pump()
            assert menu.isVisible() and menu.watcher.isActive()
            point=menu.frameGeometry().bottomRight()+QPoint(20,20)
            with patch.object(menu,'mouse_buttons',return_value={1}),patch('tray_menu.QCursor.pos',return_value=point):
                menu.buttons.clear();menu.poll_outside()
            assert not menu.isVisible() and not menu.watcher.isActive()
            checks.append('Tray popup dismisses on an outside pointer press and stops watching when hidden.')
        finally:
            runtime.close();shutdown_ui(app)


if __name__=='__main__':
    output=Path(sys.argv[-1]);output.mkdir(parents=True,exist_ok=True)
    checks=[]
    try:run(output,checks);report=dict(passed=True,checks=checks)
    except Exception:report=dict(passed=False,checks=checks,error=traceback.format_exc())
    (output/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    sys.exit(0 if report['passed'] else 1)
