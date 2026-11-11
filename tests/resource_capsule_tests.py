"""Test the real resource controls with isolated readings and a simulated taskbar."""
import copy
import time
from pathlib import Path
from unittest.mock import patch
from PyQt5.QtCore import QPoint,QPointF,Qt,QRect,QEvent
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtWidgets import QApplication


def drag(window,delta):
    pos=QPoint(min(30,window.width()//2),12);start=window.mapToGlobal(pos)
    for kind,local,global_point,button,held in [
            (QEvent.MouseButtonPress,pos,start,Qt.LeftButton,Qt.LeftButton),
            (QEvent.MouseMove,pos+delta,start+delta,Qt.NoButton,Qt.LeftButton),
            (QEvent.MouseButtonRelease,pos,start+delta,Qt.LeftButton,Qt.NoButton)]:
        QApplication.sendEvent(window,QMouseEvent(kind,QPointF(local),QPointF(global_point),button,held,Qt.NoModifier))


def auto_fold_checks(service, window, app, checks):
    from PyQt5.QtWidgets import QMenu
    from ui_test_events import Events

    outside = window.geometry().bottomRight() + QPoint(35, 35)
    with patch('resource_panel.QCursor.pos', return_value=outside) as cursor:
        assert service.set_options(resource_auto_hide=True, resource_delay=1)
        assert window.auto_fold_timer.isActive()
        menu = QMenu(window)
        menu.addAction('测试菜单')
        menu.popup(outside)
        app.processEvents()
        assert app.activePopupWidget() is menu
        Events.qWait(1400)
        assert not service.compact
        menu.hide()
        menu.deleteLater()
        Events.qWait(1800)
        assert service.compact and not service.cfg['resource_collapsed']
        assert not window.auto_fold_timer.isActive()

        cursor.return_value = window.desktop_rect().center()
        assert service.fold(False)
        Events.qWait(1400)
        assert not service.compact
        cursor.return_value = outside
        Events.qWait(1800)
        assert service.compact and not window.auto_fold_timer.isActive()
        assert service.set_options(resource_auto_hide=False)
        assert not window.auto_fold_timer.isActive()
    checks.append('Resource auto-fold follows the cursor and configured delay without a leave event, pauses for menus, resumes when they close, and stops polling when folded or disabled.')


def component_drag_checks(api, service, window, app, checks):
    from resource_options import component_location
    from ui_test_events import Events

    cfg=service.cfg
    original=copy.deepcopy({key:cfg[key] for key in ('resource_component_locations','resource_component_order',
                                                     'resource_card_layouts','resource_collapsed',
                                                     'clock_enabled','clock_locked','clock_layout')})
    try:
        assert service.fold(False)
        traffic=window.page_buttons['traffic'];resources=window.page_buttons['resources']
        assert traffic.isVisible() and resources.isVisible()
        before=resources.mapToGlobal(QPoint(4,resources.height()//2))
        Events.drag(traffic,traffic.rect().center(),before-traffic.mapToGlobal(traffic.rect().center()))
        app.processEvents()
        order=api.load_config()['resource_component_order']
        assert order.index('traffic')<order.index('resources')

        work=window.screen().availableGeometry()
        drop=work.bottomRight()-QPoint(100,100)
        assert not window.geometry().contains(drop)
        delta=drop-traffic.mapToGlobal(traffic.rect().center())
        with patch.object(api,'save_config',return_value=False):Events.drag(traffic,traffic.rect().center(),delta)
        assert component_location(cfg,'traffic')=='capsule' and not service.detached('traffic')
        Events.drag(traffic,traffic.rect().center(),delta);app.processEvents()
        card=service.detached('traffic')
        assert card and card.isVisible() and card.geometry().contains(drop)
        assert not traffic.isVisible() and component_location(api.load_config(),'traffic')=='desktop'

        assert service.fold(True)
        handle=QPoint(25,15)
        Events.drag(card,handle,window.geometry().center()-card.mapToGlobal(handle));app.processEvents()
        assert not service.compact and window.page_key=='traffic' and service.detached('traffic') is None
        assert component_location(api.load_config(),'traffic')=='capsule' and window.tab_drag is None

        from card_snap import drop_rect
        from screen_layout import capture, screen_records
        clock_layout=capture(drop_rect(drop,290,160),screen_records(),density=cfg['card_scale']/100)
        assert service.set_options(clock_enabled=True,clock_locked=False,clock_layout=clock_layout)
        clock=service.runtime.clock;assert clock.isVisible() and clock.parentWidget() is None
        handle=QPoint(32,32)
        Events.drag(clock,handle,window.geometry().center()-clock.mapToGlobal(handle));app.processEvents()
        assert window.page_key=='clock' and clock.parentWidget() is window.view('clock').host
        tab=window.page_buttons['clock'];point=tab.rect().center()
        Events.drag(tab,point,drop-tab.mapToGlobal(point));app.processEvents()
        assert component_location(api.load_config(),'clock')=='desktop'
        assert clock.isVisible() and clock.parentWidget() is None and cfg['clock_layout']==clock_layout
        checks.append('Capsule tabs reorder and persist via pointer events, detach at the drop point, and return via a folded capsule. Native clock transfers both ways and preserves its saved desktop layout. A failed save keeps the original tab.')
    finally:
        service.set_options(**original)


def run(api,runtime,root,app,output,checks):
    from run_isolated_test import assert_isolated
    assert_isolated()
    from bluetooth_gauge import devices,tray_icon
    from resource_options import DEFAULTS,FAN_METRICS,METRICS
    from resource_panel import display_values
    from resource_settings import ResourceOptions
    from resource_metrics import network_rates,busiest_engine
    from resource_taskbar import free_slot,Placement
    from resource_fps import FrameRates
    from config_transfer import normalize
    from dock_extras import DockQuickSettings
    service=runtime.resources;cfg=runtime.dock.cfg;original=copy.deepcopy(cfg)
    original_game=runtime.game_active;runtime.game_active=False;popup=options=None
    try:
        cfg.update(copy.deepcopy(DEFAULTS));cfg.update(resource_hide_unavailable=False,resource_edge_snap=False,resource_auto_hide=False);service.sync()
        assert service.window is None and service.job is None and service.bluetooth is None
        assert service.fps is None and service.sensors is None and service.history is None
        assert service.set_options(resource_bt_tray=True)
        bt=service.bluetooth;assert bt.tray and service.window is None and service.signature is None
        raw=[dict(id=f'{i:012X}',name=name,level=level) for i,(name,level) in enumerate(
            [('耳机',74),('旅行键盘',38),('无线鼠标',100),('触控笔',None),('演示器',0)],1)]
        data=devices(raw+[dict(raw[0],level=None)])
        bt.publish(data,'');first=[r['id'] for r in bt.group()];assert len(first)==3 and bt.pages()==2
        assert len({r['ink'] for r in bt.group()})==3
        before=dict(bt.assignments)
        bt.publish(devices(list(reversed(raw))),'')
        assert first==[r['id'] for r in bt.group()] and before==bt.assignments
        bt.turn(1);assert [r['level'] for r in bt.group()]==[None,0]
        assert '未报告' in bt.tray.toolTip() and '0%' in bt.tray.toolTip()
        bt.turn(-1);assert tray_icon(bt.group(),False).pixmap(32,32).save(str(output/'bluetooth-tray-rings.png'))
        cfg['resource_collapsed'] = False
        popup=DockQuickSettings(runtime.dock.extras);popup.refresh();popup.tiles['resources'].click();app.processEvents()
        assert cfg['resource_enabled'] and service.window is not None
        assert popup.tiles['resources'].value == '已开启' and popup.tiles['resources'].active
        popup.tiles['resources'].click()
        assert not cfg['resource_enabled'] and service.window is None and service.bluetooth is bt
        assert popup.tiles['resources'].value == '已关闭' and not popup.tiles['resources'].active
        popup.tiles['resources'].click();app.processEvents()
        window=service.window;assert window and window.isVisible() and not cfg['resource_collapsed']
        assert service.active_keys()=={'cpu','cpu_cores','memory','network','rank','gpu','traffic','system_status'}
        assert service.set_options(resource_bluetooth=True,resource_fps=True,resource_cpu_temp=True,resource_cpu_power=True,
                                   resource_gpu_temp=True,resource_gpu_power=True,resource_palette='vivid')
        assert service.bluetooth is bt and service.fps and service.sensors and service.sensors.keys=={'cpu_temp','cpu_power','gpu_temp','gpu_power','brightness',*FAN_METRICS}
        from taskbar_readout import columns
        with patch.dict(cfg,resource_task_metrics=list(FAN_METRICS)):
            for missing in FAN_METRICS:
                service.sensors.values={key:dict(label=METRICS[key],source='测试转速计',value=0 if key=='gpu_fan' else 1200)
                                        for key in FAN_METRICS if key!=missing}
                expected={key:('0 RPM' if key=='gpu_fan' else '1200 RPM') for key in FAN_METRICS if key!=missing}
                for compact in (False,True):
                    assert {key:value for key,_,value,_ in display_values(service,compact) if key in FAN_METRICS}==expected
                assert {cell[2]:cell[1] for group in columns(service) for cell in group if cell}=={
                    key:value.replace(' ','') for key,value in expected.items()}
        checks.append('Fan readings: CPU, GPU and board support actual zero and hide missing RPM in both capsule states and in the taskbar.')
        assert not service.job  # No live sampling on the private desktop.
        service.fps.value=59.8;service.fps.name='渲染示例'
        service.sensors.values={key:dict(label=label,value=value,source='测试驱动') for key,label,value in
                                [('cpu_temp','CPU 温度',53.2),('gpu_temp','GPU 温度',47),('gpu_power','GPU 板卡功率',1.26)]}
        now=time.monotonic()
        import math
        programs=[('记事本',12,7.1,254*2**20),('文件管理器',13,5.4,162*2**20),('照片',14,4.0,138*2**20),('画图',15,2.8,384*2**20),('终端',16,1.3,95*2**20)]
        import os
        winroot=Path(os.environ.get('SystemRoot',r'C:\\Windows'))
        icons={12:str(winroot/'System32'/'notepad.exe'),13:str(winroot/'explorer.exe'),14:str(winroot/'System32'/'SnippingTool.exe'),15:str(winroot/'System32'/'mspaint.exe'),16:str(winroot/'System32'/'cmd.exe')}
        for n in range(61):
            service.accept_sample({'time':now-60+n,'cpu':24+7*math.sin(n/3),'cpu_cores':[(7+i*37+n*5)%93 for i in range(20)],
                                   'memory':(54.,8.64*2**30,16*2**30),'network':(65000+35000*math.sin(n/3),29000+17000*math.cos(n/5)),'gpu':28+n%9,
                                   'rank':{'paths':icons,'cpu':programs,'memory':sorted(programs,key=lambda entry:entry[3],reverse=True)}})
        values={r[0]:r[2] for r in display_values(service)}
        assert values['cpu_power']=='—' and values['gpu_temp']=='47 °C' and values['fps']=='60'
        assert window.graph.isVisible() and window.rings.isVisible()
        app.processEvents();window.body.activate()
        assert window.graph.geometry().right() < window.rank_section.x()
        assert window.rank_section.geometry().bottom() < window.battery_section.y()
        assert window.sensor_columns.y() == window.battery_section.y()
        assert window.sensor_columns.geometry().right() < window.battery_section.x()
        assert window.rings.value_x==window.rings.name_x+window.rings.name_width+window.rings.gap
        assert window.rings.height()==51 and window.rings.value_x<155
        old_value_x=window.rings.value_x
        window.rings.resize(window.rings.width()+120,window.rings.height());window.rings.grab()
        assert window.rings.value_x==old_value_x and '旅行键盘' in window.rings.toolTip()
        assert window.grab().save(str(output/'resource-expanded.png'))
        regular = window.geometry()
        window.resize(500, regular.height());app.processEvents();window.body.activate()
        assert window.sensor_columns.y() == window.battery_section.y()
        assert window.rank_section.x() == window.battery_section.x()
        boxes = {key: label_area for key, _, _, label_area, _ in window.sensor_columns.cells}
        assert boxes['gpu_temp'].top() == boxes['gpu_power'].top()
        assert window.grab().save(str(output/'resource-expanded-500.png'))
        window.setGeometry(regular);app.processEvents()
        assert window.graph.rows['cpu'][1] and 'cpu_cores' not in service.history[-1]
        window.rank_buttons['memory'].click()
        assert window.rank_by=='memory' and window.rank_labels[0][1].text()=='画图'
        window.rank_buttons['cpu'].click()
        assert window.rank_labels[0][1].text()=='记事本'
        window.scroll.verticalScrollBar().setValue(window.scroll.verticalScrollBar().maximum());app.processEvents()
        assert window.grab().save(str(output/'resource-devices.png'))
        window.scroll.verticalScrollBar().setValue(0)
        from PyQt5.QtCore import QSize
        from PyQt5.QtGui import QColor,QImage,QPixmap,QPainter,QLinearGradient,QRegion
        from PyQt5.QtWidgets import QWidget
        def surface_pixels(card):
            image=QImage(card.size(),QImage.Format_ARGB32_Premultiplied);image.fill(Qt.transparent)
            painter=QPainter(image);card.render(painter,QPoint(),QRegion(),QWidget.DrawChildren);painter.end()
            return image.pixelColor(5,round(card.height()*.26)),image.pixelColor(card.width()-6,round(card.height()*.79))
        old_style={key:cfg[key] for key in ('panel_theme','panel_material','panel_color','panel_opacity')}
        for mode,base,end,tint in [('light','#d2ebe9','#cad9f4','#739fbd'),('dark','#22314d','#31364c','#4b6178')]:
            cfg.update(panel_theme=mode,panel_material='liquid',panel_color=tint,panel_opacity=42)
            window.sync_window();app.processEvents();window.glass.clear()
            scale=window.devicePixelRatioF()
            wall=QPixmap(round(window.width()*scale),round(window.height()*scale));wall.setDevicePixelRatio(scale)
            painter=QPainter(wall);gradient=QLinearGradient(0,0,window.width(),window.height())
            gradient.setColorAt(0,QColor(base));gradient.setColorAt(1,QColor(end));painter.fillRect(window.rect(),gradient);painter.end()
            with patch.object(runtime.dock,'preview',False),patch('capsule_glass.capture',return_value=wall) as capture:
                image=window.grab()
                assert capture.call_count==1 and window.glass.image is not None
                previous=window.glass.image.cacheKey()
                service.display();window.grab()
                assert capture.call_count==1 and previous==window.glass.image.cacheKey()
                assert window.colors['light']==(mode=='light')
            surfaces=[]
            for card in (window.graph,window.rank_section,window.sensor_columns,window.battery_section):
                start,end=surface_pixels(card)
                assert start.alpha()==end.alpha()==204,(mode,card.tone,start.getRgb(),end.getRgb())
                assert max(abs(a-b) for a,b in zip(start.getRgb()[:3],end.getRgb()[:3]))>=10
                surfaces.append(start.name())
            assert len(set(surfaces))==4
            assert image.save(str(output/('resource-'+mode+'.png')))
            if mode=='light':
                cfg.update(resource_bluetooth=False,resource_cpu_temp=False,resource_cpu_power=False,resource_gpu_temp=False,resource_gpu_power=False,resource_fps=False)
                window.sync_window();app.processEvents();window.glass.clear()
                with patch.object(runtime.dock,'preview',False),patch('capsule_glass.capture',return_value=wall):
                    assert window.grab().save(str(output/'resource-overview.png'))
                cfg.update(resource_bluetooth=True,resource_cpu_temp=True,resource_cpu_power=True,resource_gpu_temp=True,resource_gpu_power=True,resource_fps=True)
                window.sync_window();app.processEvents()
        cfg.update(panel_material='clear',panel_opacity=0);window.sync_window()
        assert window.grab().save(str(output/'resource-clear-dark.png')) and window.glass.image is None
        clear,_=surface_pixels(window.graph)
        assert clear.name()!=surfaces[0] and clear.alpha()==204
        cfg.update(old_style);window.sync_window()
        narrow=window.geometry();window.resize(380,narrow.height());app.processEvents();window.body.activate()
        assert window.graph.geometry().bottom() < window.rank_section.y()
        assert window.rank_section.geometry().bottom() < window.sensor_columns.y()
        assert window.sensor_columns.geometry().bottom() < window.battery_section.y()
        scroll = window.scroll.verticalScrollBar()
        assert scroll.maximum() > 0
        scroll.setValue(scroll.maximum());app.processEvents()
        assert window.grab().save(str(output/'resource-expanded-380.png'))
        scroll.setValue(0)
        window.setGeometry(narrow);app.processEvents()
        options=ResourceOptions(service);options.show();app.processEvents()
        for page,fields in ((1,options.task_fields),(2,options.compact_fields),(5,options.limit_fields)):
            options.tabs.setCurrentIndex(page)
            assert all(key in fields for key in FAN_METRICS)
        options.tabs.setCurrentIndex(0)
        options.fields['resource_layer'].setCurrentIndex(options.fields['resource_layer'].findData('top'))
        assert options.commit() and cfg['resource_layer']=='top'
        options.tabs.setCurrentIndex(4)
        transparency=options.fields['resource_card_transparency']
        assert transparency.value()==20 and transparency.parentWidget().slider.value()==20
        transparency.parentWidget().slider.setValue(37)
        options.tabs.setCurrentIndex(0);options.tabs.setCurrentIndex(4)
        transparency=options.fields['resource_card_transparency']
        assert transparency.value()==37 and transparency.parentWidget().slider.value()==37
        source=options.fields['resource_background']
        source.setCurrentIndex(source.findData('custom'))
        field=options.custom_fields['material'];field.setCurrentIndex(field.findData('solid'))
        field=options.custom_fields['theme'];field.setCurrentIndex(field.findData('dark'))
        options.custom_fields['opacity'].setValue(82);options.color.setText('#263847')
        assert options.commit() and window.background['material']=='solid' and window.background['color']=='#263847'
        assert cfg['resource_card_transparency']==37==api.load_config()['resource_card_transparency']
        assert normalize(cfg,api)['resource_card_transparency']==37
        assert surface_pixels(window.graph)[0].alpha()==161
        stored=cfg['resource_appearance'].copy();assert normalize(cfg,api)['resource_appearance']==stored
        service.set_options(panel_color='#f18899');assert window.background==stored
        source.setCurrentIndex(source.findData('global'));assert options.commit() and window.background['color']=='#f18899'
        source.setCurrentIndex(source.findData('custom'));assert options.commit() and window.background==stored
        options.reject()
        for value,alpha in ((100,0),(0,255),(20,204)):
            assert service.set_options(resource_card_transparency=value)
            assert surface_pixels(window.graph)[0].alpha()==alpha
        checks.append('Capsule card transparency defaults to 20%, persists slider changes across tabs and reload, and renders both end values.')
        assert service.set_options(resource_collapsed=True,resource_fold='pill',resource_auto_hide=False)
        assert service.active_keys()=={'cpu','network','memory','gpu','traffic'}
        seen=time.monotonic()
        readings={'cpu':19.,'network':(42000,7000),'memory':(54.,8.64*2**30,16*2**30)}
        service.accept_sample(dict(readings,time=seen))
        for _ in range(3):
            service.fold(False);service.accept_sample(dict(time=seen+.1,cpu=None,network=None))
            assert all(service.latest[k]==v for k,v in readings.items())
            service.fold(True)
        service.accept_sample(dict(time=seen+.2,cpu=0.,network=(0,0)))
        assert service.latest['cpu']==0 and service.latest['network']==(0,0)
        service.accept_sample(dict(time=seen+20,cpu=None,network=None))
        assert 'cpu' not in service.latest and 'network' not in service.latest
        service.accept_sample(dict(readings,time=time.monotonic()))
        assert window.grab().save(str(output/'resource-compact.png'))
        old=window.geometry();drag(window,QPoint(57,37));app.processEvents()
        assert cfg['resource_layout'] and window.geometry().topLeft()!=old.topLeft()
        anchor=copy.deepcopy(cfg['resource_layout']);center=window.geometry().center().x();top=window.y()
        service.fold(False);assert abs(window.geometry().center().x()-center)<=1 and window.y()==top
        service.fold(True);assert cfg['resource_layout']==anchor
        service.set_options(resource_fold='ball')
        assert window.width()==window.height() and service.active_keys()=={'traffic'} and service.fps is None and service.sensors is None
        assert service.bluetooth is bt  # The independently enabled tray still needs the reader.
        service.set_options(resource_bt_tray=False)
        assert service.bluetooth is None
        service.set_options(resource_fold='pill',resource_task_font=10)
        component_drag_checks(api, service, window, app, checks)
        bar={'rect':QRect(0,740,1366,28),'screen':'test-monitor','hwnd':1,'map':(0,0,0,0,1,1)}
        blocked=[QRect(0,740,350,28),QRect(1100,740,266,28)]
        def query(place,b,r):
            blocks=[b['rect']] if b['screen']=='occupied-screen' else blocked
            place.accept_probe(b,r,{'ok':True,'blocks':[[q.left(),q.top(),q.right()+1,q.bottom()+1] for q in blocks]})
        with patch.object(Placement,'bars',return_value=[bar]),patch.object(Placement,'query',query):
            monitor_settings={'resource_taskbar':True,'resource_taskbar_position':'right',
                              'resource_taskbar_anchor':{'screen':bar['screen'],'ratio':.88}}
            assert service.set_options(**monitor_settings)
            strip=service.strip;assert strip and strip.isVisible() and window.isVisible()
            original_slot=QRect(strip.geometry())

            def drop_capsule(x,destination=bar):
                pos=window.mapToGlobal(QPoint(min(30,window.width()//2),12))
                center=window.geometry().center()
                with patch.object(window,'taskbar_at',return_value=destination):
                    drag(window,QPoint(x-center.x(),destination['rect'].center().y()-pos.y()));app.processEvents()

            drop_capsule(460)
            assert cfg['resource_capsule_taskbar'] and cfg['resource_layout']==anchor
            pin=window.taskbar_placement
            assert service.compact and pin.slot.contains(window.geometry())
            assert bar['rect'].contains(pin.slot) and all(not pin.slot.intersects(r) for r in [*blocked,original_slot])
            assert cfg['resource_capsule_taskbar_position']=='custom'
            assert abs(cfg['resource_capsule_taskbar_anchor']['ratio']-460/1366)<.01
            assert window.grab().save(str(output/'resource-pinned-capsule.png'))
            drop_capsule(686)
            assert abs(pin.ratio-686/1366)<.01
            assert all(cfg[key]==value for key,value in monitor_settings.items()) and strip.geometry()==original_slot
            persisted=api.load_config()
            assert all(persisted[key]==value for key,value in monitor_settings.items())
            assert persisted['resource_capsule_taskbar_anchor']==cfg['resource_capsule_taskbar_anchor']

            old_pin=QRect(pin.slot);pin_anchor=copy.deepcopy(cfg['resource_capsule_taskbar_anchor'])
            drop_capsule(700,dict(bar,screen='occupied-screen'))
            assert pin.slot==old_pin and cfg['resource_capsule_taskbar_anchor']==pin_anchor
            with patch.object(api,'save_config',return_value=False):drop_capsule(500)
            assert pin.slot==old_pin and cfg['resource_capsule_taskbar_anchor']==pin_anchor
            drag(window,QPoint());app.processEvents()
            assert not service.compact and window.geometry().bottom()<bar['rect'].top()
            assert window.grab().save(str(output/'resource-pinned-expanded.png'))
            service.fold(True)
            assert pin.slot==old_pin and pin.slot.contains(window.geometry())
            assert service.set_options(resource_capsule_taskbar=False)
            assert not window.taskbar_placement and cfg['resource_layout']==anchor
            assert all(cfg[key]==value for key,value in monitor_settings.items()) and strip.geometry()==original_slot
        assert bar['rect'].contains(original_slot) and all(not original_slot.intersects(r) for r in blocked)
        checks.append('Dragging the capsule onto the taskbar and adjusting it preserves the independent right-aligned monitor slot and settings, including on disk. Both avoid occupied areas. Failed drops restore the capsule. Click expands above the taskbar and unpin restores the desktop anchor.')
        service.set_options(resource_enabled=False)
        assert not service.window and strip.isVisible() and service.active_keys()=={'memory','network'}
        service.sensors.values=dict(cpu_temp=dict(label='CPU 温度',source='测试传感器',value=61.6),gpu_temp=dict(label='GPU 温度',source='测试传感器',value=44.0),
                                    cpu_power=dict(label='CPU 封装功率',source='测试传感器',value=8.89),gpu_power=dict(label='GPU 板卡功率',source='测试传感器',value=1.24))
        service.fps.value=44;service.fps.name='测试前台应用'
        service.accept_sample(dict(time=time.monotonic(),network=(83000,49100),memory=(73.9,8,16)))
        strip.refresh();app.processEvents();pm=strip.grab()
        assert len(strip.cells)==4 and strip.page_count>=1 and '61.6°C' in strip.toolTip()
        assert strip.single_line or strip.page_count==1
        assert pm.save(str(output/'taskbar-monitor-two-lines.png'))
        strip.resize(83,30);strip.grab();assert strip.page_count>1
        with patch.object(strip.placement,'bars',return_value=[]):drag(strip,QPoint(-43,-115))
        assert service.strip is strip and not service.window and cfg['resource_taskbar'],'Taskbar content must not be repositioned by dragging'
        service.return_from_taskbar(QPoint(150,180))
        window=service.window
        assert window and not service.strip and not cfg['resource_taskbar'] and cfg['resource_layout']!=anchor and cfg['resource_layer']=='top'
        # Enable from its own Quick tile, with the desktop and tray independently disabled.
        service.set_options(resource_enabled=False)
        with patch.object(Placement,'bars',return_value=[bar]),patch.object(Placement,'query',query):
            popup.tiles['taskbar_monitor'].click();app.processEvents()
            assert service.strip.isVisible() and not service.window and not service.bluetooth and service.sensors and service.fps
            popup.tiles['taskbar_monitor'].click();app.processEvents()
            assert not service.window and not service.strip and not service.signature and not service.fps and not service.sensors
        service.open();window=service.window
        assert free_slot(bar['rect'],[bar['rect']],.5) is None
        v=free_slot(QRect(-58,0,58,900),[QRect(-58,0,58,200)],.6);assert v and v.width()==54 and v.y()>=200
        assert normalize(cfg,api)['resource_layout']==cfg['resource_layout']
        old_docked=dict(cfg,resource_enabled=True,resource_taskbar=True);old_docked.pop('resource_task_metrics')
        upgraded=normalize(old_docked,api)
        assert upgraded['resource_taskbar'] and not upgraded['resource_enabled'] and 'memory' in upgraded['resource_task_metrics']
        long_names=[dict(row,name='非常长的旅行机械键盘和触控笔设备名称') for row in raw[:1]]
        bt_only={'resource_'+key:key=='bluetooth' for key in __import__('resource_options').METRICS}
        service.set_options(**bt_only,resource_layout={},resource_collapsed=False,
                            resource_expanded_width=560,resource_expanded_height=300)
        service.bluetooth.publish(devices(long_names),'');app.processEvents();window.grab()
        assert window.width()<=280 and not window.graph.isVisible() and window.rings.isVisible() and window.rings.name_width<=112
        assert long_names[0]['name'] in window.rings.toolTip()
        all_off={'resource_'+key:False for key in __import__('resource_options').METRICS}
        assert service.set_options(**all_off) and not service.signature and not service.history and not service.bluetooth and not service.fps and not service.sensors
        service.set_options(resource_cpu=True);runtime.game_active=True;service.sync()
        assert service.window is None and service.signature is None and service.history is None
        runtime.game_active=False;service.sync();assert service.window
        auto_fold_checks(service, service.window, app, checks)
        service.set_options(resource_enabled=False);assert not service.window and not service.signature
        assert network_rates({1:(100,30)},{1:(150,70),2:(10000000,9900)},2)==(25,20)
        assert network_rates({1:(100,30)},{1:(4,2)},2) is None
        assert busiest_engine({'pid_1_luid_0x1_0x2_phys_0_eng_1_engtype_3D':15,'pid_2_luid_0x1_0x2_phys_0_eng_1_engtype_3D':25,'pid_1_luid_0x1_0x2_phys_0_eng_2_engtype_Copy':12})==40
        assert busiest_engine({}) is None
        from resource_fps import FrameSources
        sources=FrameSources()
        for i in range(8):
            sources.add(13,'dwm.exe','main',20,i*.02)
            sources.add(14,'fixture.exe','main',25,i*.025)
        assert sources.pick(14,.25)[:2]==(40.,'前台 · fixture.exe') and sources.pick(0,.25)[0]==50.
        assert sources.pick(14,8)[0] is None
        from resource_processes import Process,group_members
        rows=[Process(pid,parent,10+pid,name,2,8) for pid,parent,name in [(1,0,'explorer'),(2,1,'BigFishDockpro'),(3,2,'BigFishDockpro'),(4,3,'TranslucentTB'),(5,1,'TranslucentTB'),(6,3,'chrome')]]
        assert group_members({r.pid:r for r in rows},3,2)=={2,3,4}
        frames=FrameRates()
        for n in range(40):frames.add('main',20,n*.02)
        frames.add('overlay',100,.1);frames.add('overlay',100,.2)
        assert frames.rate(.9)==50 and frames.rate(5) is None
        checks.append('Resource capsule UI: responsive side-by-side graphs and process ranking, theme-aware wallpaper glass cached across samples, dark/light/transparent backgrounds, actual Quick tile, independent Bluetooth tray, stable multi-device rings and pages, 0 vs unknown, per-metric demand and full release, real layer control and dragging, header-centred fold, taskbar vertical slots, import and game suspension. Network counter resets, per-engine GPU aggregation and sampled frame intervals checked with fixtures.')
    finally:
        if options:options.reject();options.deleteLater()
        if popup:popup.close();popup.deleteLater()
        runtime.game_active=original_game
        cfg.clear();cfg.update(original);service.sync();api.save_config(cfg)
