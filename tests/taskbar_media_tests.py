"""Taskbar media transport and centered glyphs in verified simulated slots."""
import copy,time
from unittest.mock import patch
from PyQt5.QtCore import Qt,QRect,QPointF,QEvent,QRectF
from PyQt5.QtGui import QMouseEvent,QPixmap,QColor,QPainter


def run(api,runtime,app,output,checks):
    from resource_options import DEFAULTS
    from resource_taskbar import Placement,free_slot
    cfg=runtime.dock.cfg;before=copy.deepcopy(cfg);service=runtime.resources
    bar=dict(rect=QRect(0,740,1366,44),screen='taskbar-design-test',hwnd=1,map=(0,0,0,0,1,1))
    def query(place,b,ratio):place.accept(b,ratio,free_slot(b['rect'],[QRect(0,740,250,44),QRect(1120,740,246,44)],ratio,wanted=place.window.preferred_width()))
    try:
        cfg.update(copy.deepcopy(DEFAULTS));cfg.update(resource_taskbar=True,resource_task_music=True,resource_enabled=False,resource_ai=False,resource_music=False,resource_lyrics=False,taskbar_text_mode='light')
        with patch.object(Placement,'bars',return_value=[bar]),patch.object(Placement,'query',query),patch('taskbar_text.read_mode',return_value=0):
            service.sync();strip=service.strip;bridge=service.deck
            assert bridge and bridge.signature[2] and not bridge.signature[0] and not service.window
            service.sensors.values={key:dict(label=label,source='测试传感器',value=value) for key,label,value in
                                   [('cpu_temp','CPU 温度',76.6),('gpu_temp','GPU 温度',52.5),('cpu_power','CPU 功耗',18.61),('gpu_power','GPU 功耗',1.49)]}
            service.fps.value=14;service.fps.name='测试播放器'
            service.accept_sample(dict(time=time.monotonic(),memory=(76.2,12,16),network=(7*1024,995*1024)))
            media=dict(type='media',tracks=[dict(id='test',source='测试播放器',title='Easy Story')],track=dict(id='test',title='Easy Story',artist='隔离测试',state='Playing',duration=200,position=100,canToggle=True,canPrevious=True,canNext=True,canSeek=True))
            bridge.accept(media)
            bridge.cover=QPixmap(48,48);bridge.cover.fill(QColor('#b79273'));bridge.levels=[.2,.6,.9,.8,.5,.4,.3,.6]
            strip.placement.check();app.processEvents();strip.refresh();assert strip.width()<480 and strip.shows_wave() and bridge.signature[5]
            for size in (2,4,6,8,11,18,24):
                cfg['resource_task_font']=size;strip.refresh();app.processEvents();strip.grab()
                assert {'Previous','PlayPause','Next','seek'}<=strip.media_actions.keys(),(size,strip.width(),strip.media_actions,__import__('taskbar_media').layout(strip))
                text=QRectF()
                for rect in strip.text_bounds:text=text.united(rect);assert QRectF(strip.rect()).contains(rect)
                assert abs(text.center().y()-strip.height()/2)<=1
                assert all(abs(rect.center().y()-strip.height()/2)<=1 for rect in strip.media_bounds)
                canvas=QPixmap(strip.size()*strip.devicePixelRatioF());canvas.setDevicePixelRatio(strip.devicePixelRatioF());canvas.fill(QColor('#202b3b'))
                painter=QPainter(canvas);strip.render(painter);painter.end();canvas.save(str(output/f'taskbar-media-centered-{size}.png'))
            # Actual occupied width shrinks with text AND enabled music parts.
            shrink=[]
            for size in (11,8,6,4,2):
                cfg['resource_task_font']=size;strip.refresh();strip.placement.check();app.processEvents();strip.grab()
                assert strip.effective_font==size and strip.page_count==1
                shrink.append(strip.width());strip.grab().save(str(output/f'taskbar-shrink-{size}.png'))
            assert all(a>b for a,b in zip(shrink,shrink[1:])),shrink
            cfg['resource_task_font']=24;strip.refresh();strip.placement.check();app.processEvents();strip.grab()
            def click(point):
                for kind,buttons in [(QEvent.MouseButtonPress,Qt.LeftButton),(QEvent.MouseButtonRelease,Qt.NoButton)]:
                    app.sendEvent(strip,QMouseEvent(kind,QPointF(point),QPointF(strip.mapToGlobal(point.toPoint())),Qt.LeftButton,buttons,Qt.NoModifier))
            with patch.object(bridge,'send') as send:
                click(strip.media_actions['PlayPause'].center());send.assert_called_with(op='PlayPause',id='test')
                click(strip.media_actions['Next'].center());send.assert_called_with(op='Next',id='test')
                click(strip.media_actions['seek'].center());assert send.call_args.kwargs['op']=='seek' and .49<=send.call_args.kwargs['fraction']<=.51
            # Keep a press tied to the original button/source while samples change.
            point=strip.media_actions['PlayPause'].center();old_rect=QRect(strip.geometry())
            app.sendEvent(strip,QMouseEvent(QEvent.MouseButtonPress,point,QPointF(strip.mapToGlobal(point.toPoint())),Qt.LeftButton,Qt.LeftButton,Qt.NoModifier))
            pending=old_rect.translated(-3,0);strip.placement.accept(strip.placement.target,strip.placement.ratio,pending)
            assert strip.geometry()==old_rect and strip.placement.deferred
            previous_id=bridge.media['track']['id'];bridge.media['track']['id']='new-player'
            with patch.object(bridge,'send') as send:
                release=point+QPointF(0,10)
                app.sendEvent(strip,QMouseEvent(QEvent.MouseButtonRelease,release,QPointF(strip.mapToGlobal(release.toPoint())),Qt.LeftButton,Qt.NoButton,Qt.NoModifier))
                send.assert_called_once_with(op='PlayPause',id=previous_id)
            bridge.media['track']['id']=previous_id;assert strip.placement.deferred is None
            positions=[]
            for alignment in ('left','center','right'):
                assert service.set_options(resource_taskbar_position=alignment);strip.placement.restore();app.processEvents();positions.append(strip.geometry().x())
                assert bar['rect'].contains(strip.geometry()) and strip.x()>=250 and strip.geometry().right()<1120
            assert positions[0]<positions[1]<positions[2]
            # Win32 hit testing preserves a first click without activating the app.
            import ctypes
            from ctypes import wintypes
            msg=wintypes.MSG();msg.message=0x0021
            assert strip.nativeEvent(b'windows_generic_MSG',ctypes.addressof(msg))==(True,3)
            msg.message=0x0084;assert strip.nativeEvent(b'windows_generic_MSG',ctypes.addressof(msg))==(True,1)
            user=ctypes.windll.user32;user.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
            user.WindowFromPoint.argtypes=[wintypes.POINT];user.WindowFromPoint.restype=wintypes.HWND
            strip.grab();app.processEvents();native=wintypes.RECT();assert user.GetWindowRect(int(strip.winId()),ctypes.byref(native))
            target=strip.media_actions['PlayPause'].center()
            hit=wintypes.POINT(native.left+round(target.x()*(native.right-native.left)/strip.width()),native.top+round(target.y()*(native.bottom-native.top)/strip.height()))
            assert user.WindowFromPoint(hit)==int(strip.winId()),'The native music hit target belongs to another window'
            # Reproduce Explorer becoming topmost over an otherwise visible strip.
            from PyQt5.QtWidgets import QWidget
            from taskbar_input import restore_input_layer
            blocker=QWidget(None,Qt.Tool|Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint|Qt.WindowDoesNotAcceptFocus)
            blocker.setAttribute(Qt.WA_ShowWithoutActivating);blocker.setStyleSheet('background:#182b40');blocker.setGeometry(strip.geometry());blocker.show();app.processEvents()
            user.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
            user.SetWindowPos(int(blocker.winId()),-1,0,0,0,0,0x13)
            assert user.WindowFromPoint(hit)==int(blocker.winId())
            assert not restore_input_layer(int(strip.winId()),1),'Must not raise over unrelated dialogs'
            assert restore_input_layer(int(strip.winId()),int(blocker.winId()))
            assert user.WindowFromPoint(hit)==int(strip.winId())
            blocker.close();blocker.deleteLater();app.processEvents()
            from itertools import chain, repeat
            with patch.object(runtime.dock, 'preview', False), patch.object(strip, 'host', strip.placement.target['hwnd']), \
                 patch('taskbar_input.has_foreign_overlay', side_effect=chain((True,), repeat(False))), \
                 patch('taskbar_input.restore_input_layer') as restore:
                strip.restore_input_layer()
                assert not strip.isVisible() and strip._yielded_to_overlay
                restore.assert_not_called()
                strip.restore_input_layer()
                assert strip.isVisible() and not strip._yielded_to_overlay
                restore.assert_called()
            for width in (280,170,83):
                strip.resize(width,40);strip.refresh();app.processEvents();strip.grab().save(str(output/f'taskbar-media-narrow-{width}.png'))
                assert all(QRectF(strip.rect()).contains(rect) for rect in strip.media_bounds+strip.text_bounds)
            cfg['resource_task_font']=11;strip.resize(480,40);bridge.configure();bridge.accept(media)
            bridge.cover=QPixmap(48,48);bridge.cover.fill(QColor('#b79273'));bridge.levels=[.2,.6,.9,.8,.5,.4,.3,.6]
            full_width=strip.preferred_width()
            cfg.update(resource_task_media_parts=['wave','progress'],resource_task_music_colorful=False)
            strip.refresh();app.processEvents();mono=strip.grab().toImage();geometry=strip.geometry();actions=dict(strip.media_actions)
            cfg['resource_task_music_colorful']=True;rainbow=strip.grab().toImage()
            assert mono!=rainbow and strip.geometry()==geometry and strip.media_actions==actions
            rainbow.save(str(output/'taskbar-music-colorful.png'))
            cfg.update(resource_task_media_parts=list(DEFAULTS['resource_task_media_parts']),resource_task_music_colorful=False)
            # Numeric colors remain independently optional; a capsule-only switch
            # cannot recolor the taskbar's system-colored text.
            cfg.update(resource_task_music=False,resource_task_metrics=['memory'],resource_task_threshold=False,resource_threshold=True)
            strip.refresh();mono=strip.grab().toImage();cfg['resource_threshold']=False
            assert strip.grab().toImage()==mono
            cfg['resource_task_threshold']=True;colored=strip.grab().toImage();assert colored!=mono
            from resource_status import threshold
            images=[]
            for value in (59.9,60,80):
                service.latest['memory']=(value,12,16);strip.refresh();img=strip.grab().toImage();images.append(img)
                assert any(img.pixelColor(x,y).name()==threshold(value,100,strip.system_mode!=0) for x in range(img.width()) for y in range(img.height()))
            assert images[0]!=images[1] and images[1]!=images[2]
            cfg.update(resource_task_threshold=False,resource_threshold=True,resource_task_music=True,resource_task_metrics=list(DEFAULTS['resource_task_metrics']))
            bridge.configure();bridge.accept(media);bridge.levels=[.2,.6,.9,.8,.5,.4,.3,.6]
            service.accept_sample(dict(time=time.monotonic(),memory=(76.2,12,16),network=(7*1024,995*1024)));strip.refresh()
            for mode,color in ((1,'#000000'),(0,'#ffffff')):
                with patch('taskbar_text.read_mode',return_value=mode):strip.sync_style();strip.grab();assert strip.foreground_ink==color
            strip.placement.check();strip.refresh();app.processEvents();strip.grab().save(str(output/'tight-taskbar.png'))
            assert strip.page_count==1
            assert min(r.left() for r in strip.text_bounds)-max(r.right() for r in strip.media_bounds)<=8
            assert strip.width()-max(r.right() for r in strip.text_bounds)<=8
            for parts in (['wave'],['cover'],['title'],['controls'],['progress'],['cover','wave']):
                cfg['resource_task_media_parts']=parts;strip.placement.check();service.sync();strip.refresh();app.processEvents();strip.grab()
                assert set(strip.media_parts_shown)==set(parts),strip.media_parts_shown
                assert strip.preferred_width()<full_width and strip.shows_wave()==('wave' in parts)
                assert service.deck.signature[5]==('wave' in parts)
                canvas=QPixmap(strip.size()*strip.devicePixelRatioF());canvas.setDevicePixelRatio(strip.devicePixelRatioF());canvas.fill(QColor('#202b3b'))
                painter=QPainter(canvas);strip.render(painter);painter.end();canvas.save(str(output/('taskbar-parts-'+'-'.join(parts)+'.png')))
            # Music alone may be narrower than the taskbar's thickness, but is
            # still a horizontal taskbar slot (not a vertical taskbar).
            cfg.update(resource_task_metrics=[],resource_task_media_parts=['cover']);strip.placement.check();service.sync();strip.refresh();app.processEvents();strip.grab()
            assert service.deck and strip.width()<=48 and strip.media_parts_shown==['cover'] and not strip.vertical()
            strip.grab().save(str(output/'taskbar-cover-only.png'))
            from resource_settings import ResourceOptions
            options=ResourceOptions(service)
            options.fields['resource_taskbar_position'].setCurrentIndex(options.fields['resource_taskbar_position'].findData('center'))
            for key,field in options.task_media_fields.items():field.setChecked(key=='wave')
            from resource_options import TASK_COLUMN_NAMES
            options.orders['resource_task_order']=['network', *[key for key in TASK_COLUMN_NAMES if key != 'network']]
            options.tabs.setCurrentIndex(2)
            assert options.commit() and api.load_config()['resource_task_media_parts']==['wave'] and api.load_config()['resource_taskbar_position']=='center';options.reject();options.deleteLater()
            assert api.load_config()['resource_task_order'][0] == 'network'
            cfg['resource_task_metrics']=list(DEFAULTS['resource_task_metrics']);cfg['resource_task_media_parts']=[];service.sync();app.processEvents()
            assert service.deck is None and service.strip
            cfg.update(resource_task_music=False,resource_task_font=11);strip.resize(288,40);service.sync();app.processEvents();strip.grab()
            assert service.deck is None and service.strip and not strip.media_actions
            text=QRectF()
            for rect in strip.text_bounds:text=text.united(rect)
            assert abs(text.center().y()-strip.height()/2)<=1
            cfg['resource_taskbar']=False;service.sync();assert not service.deck and not service.strip and not service.signature
        checks.append('Taskbar media: independent/persisted cover/title/controls/wave/progress including icon-only and spectrum-only; fixed left/center/right placement avoids blocked regions; press locks source/button and defers placement, first-click native handling and WindowFromPoint hit target; click/seek routing, 8/11/18/24 fonts centered vertically, 40–480 widths with safe paging, disabling media releases the shared helper. Simulated taskbar on a private desktop; no playback commands sent.')
    finally:
        cfg.clear();cfg.update(before);service.sync();api.save_config(cfg)
