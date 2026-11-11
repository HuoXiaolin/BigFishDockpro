"""Hot-switch regressions with native windows, unchanged anchors and coherent work areas."""
import copy,ctypes,json
from pathlib import Path
from unittest.mock import patch


def run(api,runtime,root,app,output,checks):
    from ctypes import wintypes
    from PyQt5.QtCore import Qt,QRect,QRectF
    from PyQt5.QtGui import QImage,QPainter,QColor
    from screen_layout import capture,project,screen_records
    from fold_options import geometry as folded
    from dpi_support import metric
    from desktop_panel_tests import wait_for
    cfg=runtime.dock.cfg;before=copy.deepcopy(cfg);layout=runtime.layout;provider=layout.screens
    actual=screen_records()[0];left,top,work_w,work_h=actual['area'];base=dict(screen=actual['screen'],area=[left,top,1920,1020])
    rect=[left+550,top+210,640,330];record=dict(base,rect=rect,density=1.0)
    dock=runtime.dock;panel=None
    user=ctypes.windll.user32;user.GetClientRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
    user.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
    user.SendMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    current=[actual]
    try:
        cfg.update(dock_visible=True,panel_enabled=True,panels_visible=True,panel_auto_hide=False,panel_locked=False,desktop_auto_sort=False,game_mode=False,fullscreen_detection=False,
        card_scale=100,icon_size=42,position='custom',custom_bottom=220,
            card_sizing={'width':320,'height':260,'font_size':10,'area':[1920,1020],'ui_scale':1.0,'density':1.0,'font_density':1.0,'version':2},
            merged_panels=True,merged_active='apps',merged_collapsed=True,merged_geometry=rect,
            desktop_panels=[{'id':key,'name':name,'merged':True,'enabled':True,'geometry':rect} for key,name in __import__('desktop_catalog').CATEGORIES],
            merge_groups=[{'id':'default','name':'演示分组','active':'apps','collapsed':True,'geometry':rect,'fold':{'style':'ball','ratio':50}}],
            display_layout={'dock':dict(base,rect=list(base['area'])),'merged':record,'panels':{},'merge_groups':{}},
            clock_enabled=True,calendar_enabled=True,clock_layout=dict(base,rect=[left+1100,top+80,450,220]),calendar_layout=dict(base,rect=[left+100,top+480,360,350]))
        cfg['items']=[{'path':str(Path(root)/('display-app-%02d.exe'%i)),'name':'演示应用 '+str(i+1)} for i in range(18)]
        # Full-size synthetic icons avoid a missing-EXE fallback masquerading
        # as an icon scaling problem in the rendered comparison.
        from PyQt5.QtGui import QPixmap,QFont
        from PyQt5.QtCore import QSize
        def test_icon(path,pixels,*args,**kwargs):
            image=QPixmap(pixels,pixels);image.fill(Qt.transparent);p=QPainter(image);p.setRenderHint(QPainter.Antialiasing)
            index=int(Path(path).stem.rsplit('-',1)[-1]);colors=('#4a9de0','#70c7b3','#e9ae58','#ce8dcc','#ef8c9d','#88a4e8')
            p.setPen(Qt.NoPen);p.setBrush(QColor(colors[index%len(colors)]));p.drawRoundedRect(QRectF(pixels*.06,pixels*.06,pixels*.88,pixels*.88),pixels*.2,pixels*.2)
            font=QFont('Segoe UI');font.setPixelSize(round(pixels*.5));font.setWeight(QFont.DemiBold);p.setFont(font);p.setPen(Qt.white);p.drawText(image.rect(),Qt.AlignCenter,chr(65+index%26));p.end();return image
        icons=patch.object(dock.icons,'get',side_effect=test_icon);icons.start()
        cfg.update(api.normalize_features(cfg));runtime.apply_settings();layout.apply();app.processEvents()
        panel=runtime.panels.windows[runtime.panels.active_for('apps')];panel.set_collapsed_geometry(True)
        assert panel.collapsed
        anchor=copy.deepcopy(cfg['display_layout']);clock_anchor=copy.deepcopy(cfg['clock_layout']);calendar_anchor=copy.deepcopy(cfg['calendar_layout'])
        # Different work-area shapes, repeated changes and returning to the first
        # screen all derive from the original user reference, never the last size.
        sizes=[(work_w,work_h),(round(work_w*2/3),round(work_h*2/3)),(round(work_w*.9),round(work_h*.60)),(work_w,work_h)]
        measures=[]
        with patch('screen_layout.screen_records',side_effect=lambda:current),patch('desktop_clock.screen_records',side_effect=lambda:current),patch('sticky_notes.screen_records',side_effect=lambda:current):
            for index,(w,h) in enumerate(sizes):
                current[:]=[dict(actual,area=[left,top,w,h])]
                layout.changed();layout.timer.stop();layout.apply_pending();assert layout.pending
                panel.store_geometry();runtime.clock.save_geometry();runtime.calendar.save_geometry()
                assert cfg['display_layout']==anchor and cfg['clock_layout']==clock_anchor and cfg['calendar_layout']==calendar_anchor
                layout.finish();app.processEvents();assert not layout.pending
                expected=project(record,current,density=1.0)
                assert list(panel.bounds())==expected,(panel.bounds(),expected)
                xratio=(expected[0]-left)/max(1,w-expected[2]);yratio=(expected[1]-top)/max(1,h-expected[3])
                assert abs(xratio-550/(1920-640))<.005 and abs(yratio-210/(1020-330))<.005
                target=folded(expected,{'style':'ball','ratio':50},metric(44,panel.ui_factor,24))
                assert panel.geometry().getRect()==tuple(target),(panel.geometry().getRect(),target)
                # The expanded rectangle and all three folded styles keep the
                # same saved anchor; no intermediate widget geometry is persisted.
                layout.applying=True
                try:
                    panel.set_collapsed_geometry(False);app.processEvents()
                    assert panel.geometry().getRect()==tuple(expected),(panel.geometry().getRect(),expected)
                    original_fold=copy.deepcopy(cfg['merge_groups'][0]['fold'])
                    for style in ('bar','capsule','ball'):
                        cfg['merge_groups'][0]['fold']={'style':style,'ratio':50}
                        panel.set_collapsed_geometry(True);app.processEvents()
                        wanted=folded(expected,{'style':style,'ratio':50},metric(44,panel.ui_factor,24))
                        assert panel.geometry().getRect()==tuple(wanted),(style,panel.geometry().getRect(),wanted)
                    cfg['merge_groups'][0]['fold']=original_fold
                finally:layout.applying=False
                client=wintypes.RECT();assert user.GetClientRect(int(panel.winId()),ctypes.byref(client))
                assert abs(client.right-panel.width()*panel.devicePixelRatioF())<=2 and abs(client.bottom-panel.height()*panel.devicePixelRatioF())<=2
                area=QRect(left,top,w,h)
                assert area.contains(dock.geometry()),(area,dock.geometry())
                assert abs(dock.geometry().center().x()-area.center().x())<=1
                bar_top,_=dock.layout_position();off=area.bottom()+1-bar_top-dock.bar_h()
                assert abs(off-220*h/1020)<=1.1
                assert dock.icon_size==max(12,round(42*min(w/1920,h/1020)))
                assert all(0<=entry[0]<=dock.width() for entry in dock.rects)
                assert dock.isVisible() and panel.collapsed and panel.width()==panel.height()
                for component in (runtime.clock,runtime.calendar):assert area.contains(component.geometry()),(area,component.geometry())
                assert cfg['display_layout']==anchor and cfg['clock_layout']==clock_anchor and cfg['calendar_layout']==calendar_anchor
                # Real widget render on a synthetic wallpaper, without capturing
                # or changing the user's desktop or display configuration.
                image=QImage(w,h,QImage.Format_ARGB32_Premultiplied);image.fill(QColor('#196ca7'))
                painter=QPainter(image)
                for window in (dock,panel,runtime.clock,runtime.calendar):painter.drawPixmap(window.x()-left,window.y()-top,window.grab())
                painter.end();assert image.save(str(Path(output)/('display-layout-%d.png'%index)))
                measures.append({'work_area':[w,h],'dock':list(dock.geometry().getRect()),'card':list(panel.geometry().getRect()),'card_expanded':expected,'icon':dock.icon_size,'dpr':panel.devicePixelRatioF()})
            assert measures[0]==measures[-1]
            # A collapsed tool window may receive a transient expanded rectangle
            # after WM_DPICHANGED. The native notification guards it before Qt
            # applies that rectangle, and the quiet-period pass repairs it.
            msg=wintypes.MSG();msg.hWnd=int(panel.winId());msg.message=0x02e0;msg.wParam=144|(144<<16)
            assert layout.native_filter.nativeEventFilter(b'windows_generic_MSG',ctypes.addressof(msg))==(False,0)
            assert layout.pending
            panel.setMinimumSize(1,1);panel.setMaximumSize(16777215,16777215);panel.resize(work_w,work_h);panel.move(left,top);app.processEvents()
            assert panel.collapsed and not panel.content.isVisible()
            panel.store_geometry();assert cfg['display_layout']==anchor
            wait_for(app,lambda:not layout.pending,seconds=4)
            assert panel.width()==panel.height() and panel.width()<100,(panel.geometry().getRect(),panel.ui_factor)
            assert cfg['display_layout']==anchor and dock.isVisible()
            # Exercise the installed native filter through a real own-HWND message.
            user.SendMessageW(int(dock.winId()),0x007e,32,(work_h<<16)|work_w)
            assert layout.pending
            wait_for(app,lambda:not layout.pending,seconds=4)
            assert cfg['display_layout']==anchor and QRect(*actual['area']).contains(dock.geometry())
            cfg['custom_bottom']=2000;layout.apply();assert QRect(*actual['area']).contains(dock.geometry());cfg['custom_bottom']=220
            # A temporary empty monitor list cannot save a fallback position.
            current.clear();layout.changed();layout.timer.stop();layout.apply_pending()
            assert layout.pending and cfg['display_layout']==anchor
            layout.settle_timer.stop();layout.finish()
            assert layout.pending and not layout.timer.isActive() and not layout.settle_timer.isActive()
            current[:]=[actual];layout.changed();wait_for(app,lambda:not layout.pending,seconds=4)
            assert cfg['display_layout']==anchor and QRect(*actual['area']).contains(dock.geometry())
            # A VM can connect before the remote display and taskbar report their final size.
            remote=dict(screen='connector|remote',area=[left,top,round(work_w*.67),round(work_h*.78)])
            hwnd=int(dock.winId())
            with patch.object(layout.native_filter,'session_hwnd',hwnd), patch.object(dock,'apply_layer',wraps=dock.apply_layer) as layer:
                user.SendMessageW(hwnd,0x02b1,3,0)  # WM_WTSSESSION_CHANGE / WTS_REMOTE_CONNECT
                assert layout.session_transition and layout.pending
                wait_for(app,lambda:layout.settle_timer.isActive(),seconds=2)
                assert layout.settle_timer.remainingTime()>1200
                current[:]=[remote]  # No second Qt signal accompanies this late update.
                dock.showMinimized()
                wait_for(app,lambda:not layout.pending,seconds=5)
                area=QRect(*remote['area'])
                assert dock.available_area()==area and area.contains(dock.geometry())
                assert abs(dock.geometry().center().x()-area.center().x())<=1
                assert dock.icon_size==max(12,round(42*min(area.width()/1920,area.height()/1020)))
                assert dock.isVisible() and not dock.isMinimized() and layer.called
                physical=wintypes.RECT();assert user.GetWindowRect(hwnd,ctypes.byref(physical))
                dpr=dock.devicePixelRatioF()
                actual_pixels=(physical.left,physical.top,physical.right-physical.left,physical.bottom-physical.top)
                assert all(abs(p-l*dpr)<=2 for p,l in zip(actual_pixels,dock.geometry().getRect()))
                assert cfg['display_layout']==anchor and not layout.session_transition
            # The normal position timer also detects an unannounced resolution change.
            current[:]=[actual]
            dock.check_position();assert layout.pending
            wait_for(app,lambda:not layout.pending,seconds=4)
            assert dock.available_area()==QRect(*actual['area']) and cfg['display_layout']==anchor
            assert not layout.timer.isActive() and not layout.settle_timer.isActive()
        # Check the native physical work rectangle wins over an older Qt work rectangle,
        # including when the taskbar reserves space at the left or top.
        def native_work_area(action, parameter, pointer, flags):
            assert action==0x0030
            work=ctypes.cast(pointer,ctypes.POINTER(wintypes.RECT)).contents
            work.left,work.top,work.right,work.bottom=48,32,1440,900
            return True
        with patch.object(user,'SystemParametersInfoW',side_effect=native_work_area):
            ratio=app.primaryScreen().devicePixelRatio()
            x,y,right,bottom=(round(edge/ratio) for edge in (48,32,1440,900))
            assert screen_records()[0]['area']==[x,y,right-x,bottom-y]
        (Path(output)/'display-transition-metrics.json').write_text(json.dumps(measures,ensure_ascii=False,indent=2),encoding='utf-8')
        checks.append('display transition: all components derive from original anchors across four resolution/aspect maps; Dock stays visible, centered and in bounds with proportional height/icon size and clamped extreme offset; native WM_DISPLAYCHANGE and WM_DPICHANGED guards protect saved positions, repair an oversized collapsed card, restore after no screens, and finish without idle polling')
        checks.append('remote-session display transition: native connect message refreshes after late work-area changes, restores a minimized Dock and its layer, preserves saved anchors, and detects a missed screen event through the existing position timer')
    finally:
        if 'icons' in locals():icons.stop()
        layout.timer.stop();layout.settle_timer.stop();layout.pending=False;layout.applying=False;layout.screens=provider
        layout.session_transition=False
        cfg.clear();cfg.update(before);api.save_config(cfg);runtime.notes.reload();runtime.apply_settings();layout.apply();app.processEvents()
