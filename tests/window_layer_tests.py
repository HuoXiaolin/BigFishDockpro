"""Native layer and pointer pass-through checks on the private test desktop."""
import copy
import ctypes as C
from ctypes import wintypes as W
from unittest.mock import patch
from PyQt5.QtCore import Qt,QRect
from PyQt5.QtWidgets import QWidget
from window_layers import TOPMOST, covers_above, desktop_layer, is_topmost, native, owner_of, restack


def run(api,runtime,app,output,checks):
    dock=runtime.dock;cfg=dock.cfg;before=copy.deepcopy(cfg)
    service=runtime.resources
    cover=QWidget(None,Qt.Tool|Qt.FramelessWindowHint|Qt.WindowDoesNotAcceptFocus)
    shell=QWidget(None,Qt.Tool|Qt.FramelessWindowHint|Qt.WindowDoesNotAcceptFocus)
    user=native()
    user.WindowFromPoint.argtypes=[W.POINT];user.WindowFromPoint.restype=W.HWND
    def hit(hwnd):
        rect=W.RECT()
        assert user.GetWindowRect(hwnd,C.byref(rect))
        return user.WindowFromPoint(W.POINT((rect.left+rect.right)//2,(rect.top+rect.bottom)//2))
    def show(window,rect):
        window.setAttribute(Qt.WA_ShowWithoutActivating)
        window.setStyleSheet('background:#182e44')
        window.setGeometry(rect);window.show()
    screen=app.primaryScreen();geo=screen.geometry()
    bar_rect=QRect(geo.left(),geo.bottom()-45,geo.width(),46)
    slot=QRect(bar_rect.left()+85,bar_rect.top()+4,238,38)
    old_auto,old_game,old_manual=runtime.auto_game,runtime.game_active,runtime.manual_game
    dock_visible=dock.isVisible()
    try:
        show(cover,geo);show(shell,bar_rect);app.processEvents()
        cover_id,shell_id=int(cover.winId()),int(shell.winId())
        assert restack(shell_id,TOPMOST)
        bar=dict(hwnd=shell_id,screen=screen.name(),rect=bar_rect,map=(0,0,0,0,1,1))
        cfg.update(resource_enabled=True,resource_collapsed=True,resource_auto_hide=False,resource_layer='top',
                   resource_taskbar=True,resource_taskbar_layer='top',resource_task_metrics=['cpu'],resource_task_music=False,
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
            service.sync();assert service.strip is strip and 'cpu' in service.active_keys()
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
        checks.append('Native full screen: both topmost readouts recover above a fullscreen HWND without stealing focus; readout keeps its verified slot and CPU sampler while Explorer is hidden. Bottom hides and returns. Two pass-through switches change real hit targets and restore input on the same HWND.')
        checks.append('Native window audit: Dock, pinned note and flash handle retain topmost status above the fullscreen HWND; unpinning the note returns it to the desktop layer.')

        from resource_settings import ResourceOptions
        dialog=ResourceOptions(service)
        try:
            dialog.show();app.processEvents()
            page=dialog.fields['resource_open_page']
            assert page.accessibleName()=='展开后默认页面'
            page.setCurrentIndex(page.findData('weather'))
            dialog.fields['resource_click_through'].setChecked(True)
            assert dialog.grab().save(str(output/'readme-open-page.png'))
            dialog.tabs.setCurrentIndex(1);app.processEvents()
            dialog.fields['resource_taskbar_click_through'].setChecked(True)
            assert dialog.grab().save(str(output/'readme-taskbar-layer.png'))
            assert dialog.commit()
            saved=api.load_config()
            assert saved['resource_open_page']=='weather' and saved['resource_click_through'] and saved['resource_taskbar_click_through']
        finally:
            dialog.close();dialog.deleteLater()
        checks.append('Resource preferences: the first page exposes the default expanded page and desktop pass-through, and the taskbar page saves its separate pass-through choice.')
    finally:
        runtime.auto_game,runtime.game_active,runtime.manual_game=old_auto,old_game,old_manual
        cover.close();shell.close();cover.deleteLater();shell.deleteLater()
        cfg.clear();cfg.update(before);service.sync();runtime.notes.sync();runtime.flash.sync()
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
