"""Native layer and pointer pass-through checks on the private test desktop."""
import copy
import ctypes as C
from ctypes import wintypes as W
from unittest.mock import patch
from PyQt5.QtCore import Qt,QRect
from PyQt5.QtGui import QColor,QPixmap
from PyQt5.QtWidgets import QWidget
from window_layers import TOPMOST, covers_above, desktop_layer, is_topmost, native, owner_of, restack


def run(api,runtime,app,output,checks):
    dock=runtime.dock;cfg=dock.cfg;before=copy.deepcopy(cfg)
    service=runtime.resources
    cover=QWidget(None,Qt.Tool|Qt.FramelessWindowHint|Qt.WindowDoesNotAcceptFocus)
    shell=QWidget(None,Qt.Tool|Qt.FramelessWindowHint|Qt.WindowDoesNotAcceptFocus)
    user=native()
    user.WindowFromPoint.argtypes=[W.POINT];user.WindowFromPoint.restype=W.HWND
    def center(hwnd):
        rect=W.RECT()
        assert user.GetWindowRect(hwnd,C.byref(rect))
        return W.POINT((rect.left+rect.right)//2,(rect.top+rect.bottom)//2)
    def hit(hwnd):return user.WindowFromPoint(center(hwnd))
    def assert_transparent_corners(window):
        image=window.grab().toImage()
        for x,y in ((0,0),(0,image.height()-1),(image.width()-1,0),(image.width()-1,image.height()-1)):
            assert image.pixelColor(x,y).alpha()==0, (window.windowTitle(),x,y)

    def wallpaper_sample(window, screen=None):
        geometry=window.frameGeometry()
        dpr=window.devicePixelRatioF()
        image=QPixmap(round(geometry.width()*dpr),round(geometry.height()*dpr))
        image.setDevicePixelRatio(dpr)
        image.fill(QColor('#e9a767'))
        return image

    def assert_no_window_accent(window):
        from taskbar_appearance import AccentPolicy,CompositionData
        read=getattr(user,'GetWindowCompositionAttribute',None)
        if read is None:return
        read.argtypes=[W.HWND,C.POINTER(CompositionData)]
        read.restype=W.BOOL
        policy=AccentPolicy()
        attribute=CompositionData(19,C.addressof(policy),C.sizeof(policy))
        if read(int(window.winId()),C.byref(attribute)):
            assert policy.state==0, (window.windowTitle(),policy.state)
    def show(window,rect):
        window.setAttribute(Qt.WA_ShowWithoutActivating)
        window.setStyleSheet('background:#182e44')
        window.setGeometry(rect);window.show()
    screen=app.primaryScreen();geo=screen.geometry()
    bar_rect=QRect(geo.left(),geo.bottom()-45,geo.width(),46)
    slot=QRect(bar_rect.left()+85,bar_rect.top()+4,238,38)
    old_auto,old_game,old_manual=runtime.auto_game,runtime.game_active,runtime.manual_game
    original_job=service.job
    dock_visible=dock.isVisible()
    try:
        show(cover,geo);show(shell,bar_rect);app.processEvents()
        cover_id,shell_id=int(cover.winId()),int(shell.winId())
        assert restack(shell_id,TOPMOST)
        bar=dict(hwnd=shell_id,screen=screen.name(),rect=bar_rect,map=(0,0,0,0,1,1))
        cfg.update(resource_enabled=True,resource_collapsed=True,resource_auto_hide=False,resource_layer='top',
                   resource_taskbar=True,resource_taskbar_layer='top',resource_task_metrics=['cpu'],resource_task_music=False,
                   resource_cpu=True,resource_memory=True,resource_compact_metrics=['cpu','memory'],
                   resource_network=False,resource_traffic=False,resource_system_status=False,resource_alert_battery=False,
                   resource_click_through=False,resource_taskbar_click_through=False,resource_taskbar_anchor={'screen':screen.name()})
        service.sync()
        w,strip=service.window,service.strip
        placement=strip.placement
        placement.target=placement.slot_bar=bar;placement.slot=slot;placement.checked=True
        focus=user.GetForegroundWindow()
        with patch.object(dock,'preview',False), patch.object(placement,'bars',return_value=[bar]) as bars, \
             patch('resource_taskbar.fullscreen_window',return_value=cover_id), \
             patch('runtime_controller.fullscreen_window',return_value=cover_id):
            placement.shell_changed()
            service.sync();app.processEvents()
            capsule_id,strip_id=int(w.winId()),int(strip.winId())
            assert owner_of(strip_id)==0 and is_topmost(strip_id) and is_topmost(capsule_id)
            assert restack(cover_id,TOPMOST)
            assert covers_above(cover_id,strip_id) and covers_above(cover_id,capsule_id)
            runtime.refresh_layers()
            assert hit(strip_id)==strip_id and hit(capsule_id)==capsule_id
            assert user.GetForegroundWindow()==focus

            # Explorer hides the bar during full screen. Leave the independent
            # top readout at the last verified position, and preserve its sampler.
            bars.return_value=[];shell.hide();placement.shell_changed()
            assert strip.isVisible() and strip.geometry()==slot and hit(strip_id)==strip_id
            runtime.auto_game=runtime.game_active=True
            service.sync();assert service.strip is strip and service.active_keys()=={'cpu'}
            assert service.job is not None and service.job.isRunning()
            runtime.auto_game=runtime.game_active=False
            service.sync();app.processEvents();w=service.window;capsule_id=int(w.winId())
            assert hit(capsule_id)==capsule_id

            cfg.update(resource_click_through=True,resource_taskbar_click_through=True)
            service.sync();app.processEvents()
            for hwnd in (capsule_id,strip_id):
                assert user.GetWindowLongW(hwnd,-20)&0x20
                assert hit(hwnd)==cover_id
            assert w.isVisible() and strip.isVisible() and is_topmost(strip_id)
            cfg.update(resource_click_through=False,resource_taskbar_click_through=False)
            service.sync();app.processEvents()
            assert int(strip.winId())==strip_id and hit(strip_id)==strip_id and hit(capsule_id)==capsule_id

            # Keep the fixture on the private desktop. Only its process identity
            # is substituted, so HWND stacking and the pointer target stay native.
            owner_pid=user.GetWindowThreadProcessId
            def other_app(hwnd,pid):
                thread=owner_pid(hwnd,pid)
                if hwnd==cover_id:pid._obj.value+=1
                return thread
            with patch.dict(cfg,component_passthrough={'resource':'apps'}):
                policy=runtime.click_policy
                point=center(capsule_id)
                policy.apply(w,point)
                assert hit(capsule_id)==capsule_id
                with patch.object(user,'GetWindowThreadProcessId',side_effect=other_app):
                    policy.apply(w,point)
                    assert hit(capsule_id)==cover_id and hit(strip_id)==strip_id
                    cover.hide();policy.apply(w,point)
                    assert hit(capsule_id)==capsule_id
                    cover.show();assert restack(cover_id,1)
                    assert desktop_layer(capsule_id,False,shell_id)
                    policy.apply(w,point)
                    assert not w.testAttribute(Qt.WA_TransparentForMouseEvents)
                    assert not policy.pointer_timer.isActive()
                    assert desktop_layer(capsule_id,True)
                policy.apply(w,point)
            runtime.click_policy.apply(w)

            cfg['resource_taskbar_layer']='bottom';service.sync()
            assert not strip.isVisible() and placement.slot==slot
            bars.return_value=[bar];shell.show();cover.hide()
            with patch('resource_taskbar.fullscreen_window',return_value=None):placement.shell_changed()
            assert strip.isVisible() and strip.geometry()==slot
            assert desktop_layer(capsule_id,False,shell_id) and not is_topmost(capsule_id)
            assert desktop_layer(capsule_id,True) and owner_of(capsule_id)==0

            cfg.update(layer='top',flash_enabled=True)
            dock.show();dock.apply_layer();runtime.flash.sync()
            identity=runtime.notes.new();assert identity
            note=runtime.notes.windows[identity];note.set_option('pinned',True)
            handles=[int(widget.winId()) for widget in (dock,note,runtime.flash.edge)]
            assert all(is_topmost(hwnd) for hwnd in handles)
            cover.show();app.processEvents();assert restack(cover_id,TOPMOST)
            assert all(covers_above(cover_id,hwnd) for hwnd in handles)
            runtime.refresh_layers()
            assert all(is_topmost(hwnd) and not covers_above(cover_id,hwnd) for hwnd in handles)
            note.set_option('pinned',False);assert not is_topmost(int(note.winId()))

            from feature_config import normalize
            assert normalize({})['panel_backdrop_mode']==normalize({})['resource_backdrop_mode']=='dynamic'
            style=dict(material='liquid',theme='light',color='',opacity=18,blur=12,highlight=0)
            cfg.update(panel_layer='top',panel_backdrop_mode='dynamic',panel_appearance_source='custom',
                       panel_material='liquid',panel_blur=12,panel_opacity=18,
                       resource_backdrop_mode='dynamic',resource_background='custom',resource_appearance=style)
            panel=next(window for window in runtime.panels.windows.values() if window.isVisible())
            panel.attach_desktop(owner=0);panel_id=int(panel.winId())
            with patch('glass_capture.capture_behind',side_effect=AssertionError('dynamic card reading wallpaper')), \
                 patch('capsule_glass.capture',side_effect=AssertionError('dynamic capsule reading wallpaper')):
                panel.refresh_wallpaper_later(0);w.sync_window()
                assert is_topmost(panel_id) and owner_of(panel_id)==0 and not panel.refresh_timer.isActive()
                for window in (panel,w):
                    assert_transparent_corners(window)
                    assert_no_window_accent(window)
                    assert window.mask().isEmpty()
                assert not w.glass.uses_wallpaper and not w.wallpaper_timer.isActive()
                # Use the real stacking and hit test with a synthetic other-app PID.
                panel_key=panel.property('clickThroughKey')
                assert restack(panel_id,TOPMOST)
                with patch.dict(cfg,component_passthrough={panel_key:'apps'}):
                    with patch.object(user,'GetWindowThreadProcessId',side_effect=other_app):
                        policy.apply(panel,center(panel_id));assert hit(panel_id)==cover_id
                        cover.hide();policy.apply(panel,center(panel_id));assert hit(panel_id)==panel_id
                        cover.show();assert restack(panel_id,TOPMOST)
                    cfg['component_passthrough']={panel_key:True};policy.apply(panel)
                    assert user.GetWindowLongW(panel_id,-20)&0x20
                    cfg['component_passthrough']={};policy.apply(panel)
                    assert hit(panel_id)==panel_id
            cfg.update(panel_layer='bottom',resource_layer='bottom')
            with patch('capsule_glass.capture',side_effect=wallpaper_sample) as wallpaper, \
                 patch('glass_capture.capture_behind',side_effect=lambda window,*_:wallpaper_sample(window)) as card_wallpaper:
                w.sync_window();assert_transparent_corners(w)
                panel.attach_desktop(owner=shell_id);panel.capture_backdrop()
                assert_transparent_corners(panel)
                assert wallpaper.called and card_wallpaper.called
            assert panel.backdrop is not None and w.glass.uses_wallpaper and w.wallpaper_timer.isActive()
            assert cfg['panel_backdrop_mode']==cfg['resource_backdrop_mode']=='dynamic'
            assert owner_of(panel_id)==shell_id and not is_topmost(panel_id)
            assert not is_topmost(int(w.winId()))

            cfg.update(flash_backdrop_mode='dynamic',flash_edge_hide=False,flash_auto_hide=False,
                       spectrum_enabled=True,spectrum_layer='top',spectrum_backdrop_mode='dynamic',
                       spectrum_style='particle_sphere',spectrum_locked=True,
                       dock_material='liquid',blur_px=12,glass=True,clear_background=False,transparency=82)
            runtime.flash.sync();runtime.sync_spectrum();app.processEvents()
            edge,flash,spectrum=runtime.flash.edge,runtime.flash.panel,runtime.spectrum
            edge.reveal(immediate=True)
            flash.input_region();mask=flash.mask()
            spectrum.resize(590,248)
            def spectrum_pixels():
                image=spectrum.grab().toImage()
                for x in (image.width()//8,image.width()*7//8):
                    for y in range(0,image.height(),9):
                        assert image.pixelColor(x,y).alpha()==0, (x,y)
                return image
            with patch('capsule_glass.capture',side_effect=AssertionError('dynamic widgets reading wallpaper')):
                for window in (edge,flash):
                    window.grab()
                    assert not window.material.uses_wallpaper
                    assert_no_window_accent(window)
                dynamic=spectrum_pixels()
                assert_no_window_accent(spectrum)
            assert mask==flash.mask() and not mask.isEmpty()
            assert is_topmost(int(spectrum.winId()))
            for window in (edge,spectrum):
                with patch.dict(cfg,component_passthrough={window.property('clickThroughKey'):True}):
                    policy.apply(window)
                    assert window.testAttribute(Qt.WA_TransparentForMouseEvents)
                policy.apply(window)
            cfg.update(flash_backdrop_mode='wallpaper',spectrum_layer='bottom')
            spectrum.apply_layer()
            with patch('capsule_glass.capture',side_effect=wallpaper_sample) as wallpaper:
                for window in (edge,flash):
                    window.grab()
                    assert window.material.uses_wallpaper
                    assert_no_window_accent(window)
                assert spectrum_pixels()!=dynamic and spectrum.material.uses_wallpaper
                assert wallpaper.call_count==3
            assert mask==flash.mask() and not is_topmost(int(spectrum.winId()))
            assert cfg['spectrum_backdrop_mode']=='dynamic'
            cfg['spectrum_layer']='top';spectrum.apply_layer()
            with patch('capsule_glass.capture',side_effect=AssertionError('topmost spectrum reading wallpaper')):
                assert spectrum_pixels()==dynamic
        checks.append('Native full screen: both topmost readouts recover above a fullscreen HWND without stealing focus; readout keeps its verified slot and CPU sampler while Explorer is hidden. Bottom hides and returns. Two pass-through switches change real hit targets and restore input on the same HWND.')
        checks.append('Native window audit: Dock, pinned note and flash handle retain topmost status above the fullscreen HWND; unpinning the note returns it to the desktop layer.')
        checks.append('Conditional pointer mode: native hit testing reaches the application only where it is under the topmost capsule. The taskbar readout keeps its own mode and desktop interaction returns when the cover disappears.')
        checks.append('Topmost cards and resource capsules reveal the live background through their rounded alpha with no window-wide accent. Bottom mode uses wallpaper and keeps the saved selection and pointer policy.')
        checks.append('Flash and spectrum switch between live transparency and wallpaper. Flash keeps its shaped input region. A wide sphere leaves the space outside its artwork transparent in both modes and restores live transparency when pinned on top.')

        from resource_settings import ResourceOptions
        dialog=ResourceOptions(service)
        try:
            dialog.show();app.processEvents()
            page=dialog.fields['resource_open_page']
            assert page.accessibleName()=='展开后默认页面'
            page.setCurrentIndex(page.findData('weather'))
            pointer=dialog.fields['resource_click_through']
            pointer.setCurrentIndex(pointer.findData('apps'))
            assert dialog.grab().save(str(output/'readme-open-page.png'))
            dialog.tabs.setCurrentIndex(1);app.processEvents()
            pointer=dialog.fields['resource_taskbar_click_through']
            pointer.setCurrentIndex(pointer.findData(True))
            assert dialog.grab().save(str(output/'readme-taskbar-layer.png'))
            backdrop=dialog.fields['resource_backdrop_mode']
            backdrop.setCurrentIndex(backdrop.findData('dynamic'))
            assert dialog.commit()
            saved=api.load_config()
            assert saved['resource_open_page']=='weather' and not saved['resource_click_through']
            assert saved['component_passthrough']['resource']=='apps' and saved['resource_taskbar_click_through']
            assert saved['resource_backdrop_mode']=='dynamic'
        finally:
            dialog.close();dialog.deleteLater()
        checks.append('Resource preferences: the first page exposes the default expanded page and desktop pass-through, and the taskbar page saves its separate pass-through choice.')
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from taskbar_appearance import BACKEND_VERSION, upgrade_installed_backend
        with TemporaryDirectory(dir=output) as directory:
            root=Path(directory);legacy=root/'2026.2';legacy.mkdir()
            (legacy/'TranslucentTB.exe').write_bytes(b'installed worker')
            payload=root/'payload';backend=payload/'backend';backend.mkdir(parents=True)
            (backend/'TranslucentTB.exe').write_bytes(b'packaged worker')
            (backend/'ExplorerTAP.dll').write_bytes(b'patched helper')
            upgraded=root/BACKEND_VERSION
            upgrade_installed_backend(payload,upgraded)
            upgrade_installed_backend(payload,upgraded)
            assert (legacy/'TranslucentTB.exe').read_bytes()==b'installed worker'
            assert (upgraded/'ExplorerTAP.dll').read_bytes()==b'patched helper'
            assert list(root.glob('taskbar-update-*'))==[]
        checks.append('Taskbar backend upgrade stages the compatible helper alongside an existing worker without overwriting its files.')
    finally:
        runtime.auto_game,runtime.game_active,runtime.manual_game=old_auto,old_game,old_manual
        cover.close();shell.close();cover.deleteLater();shell.deleteLater()
        # Release the real CPU sampler before restoring the other fixtures' metrics.
        job=service.job
        if job is not None and job is not original_job:
            job.requestInterruption()
            assert job.wait(4000), 'The layer fixture left its sampler running'
            app.processEvents()
        cfg.clear();cfg.update(before);service.sync();runtime.notes.sync();runtime.flash.sync()
        runtime.panels.apply_settings()
        runtime.sync_spectrum()
        dock.setVisible(dock_visible);api.save_config(cfg)


def bluetooth_rings(checks):
    from bluetooth_gauge import ring_ink,tray_icon

    def red_pixels(level,dark):
        icon=tray_icon([dict(level=level,ink='#5b8def')],dark)
        image=icon.pixmap(32,32).toImage()
        return sum(c.alpha()>64 and c.red()>max(c.green(),c.blue())+50
                   for c in (image.pixelColor(x,y) for x in range(32) for y in range(32)))
    for dark in (False,True):
        assert red_pixels(0,dark)>0 and red_pixels(14,dark)>0
        assert red_pixels(15,dark)==red_pixels(None,dark)==0
        colors={ring_ink(dict(level=n,ink='#5b8def'),not dark) for n in (0,7,14)}
        assert len(colors)==3
    checks.append('Bluetooth ring paint: the red shade deepens below 15% in both themes; 15% retains the device color, and unknown remains a dotted neutral ring.')
