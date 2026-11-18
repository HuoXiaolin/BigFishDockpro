"""Exercise watermark settings, rendered glyphs and Windows input pass-through."""
import ctypes
from ctypes import wintypes
from unittest.mock import patch

from PyQt5.QtCore import QRect, QRectF, Qt
from PyQt5.QtWidgets import QWidget

from desktop_watermark import single_geometry, tile_centers
from dock_extras import DockQuickSettings
from settings_catalog import WIDGETS
from settings_dialog import SettingsDialog
from tray_menu import common_actions
from ui_style import AlignedMenu
from window_layers import covers_above, is_topmost, native, restack, TOPMOST


def run(api, runtime, app, checks):
    cfg = runtime.dock.cfg
    original = {k:v for k,v in cfg.items() if k.startswith('watermark_')}
    manager = runtime.watermarks
    assert not manager.windows and not cfg['watermark_enabled']
    dialog = SettingsDialog(runtime.tray, api)
    menu = AlignedMenu()
    quick = DockQuickSettings(runtime.dock.extras)
    receiver = QWidget(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus)
    receiver.setAttribute(Qt.WA_ShowWithoutActivating)
    screen = app.primaryScreen()
    try:
        dialog.tabs.setCurrentIndex(WIDGETS);dialog.show()
        dialog.set_draft_values(dict(watermark_enabled=True, watermark_color='#5599dd', watermark_opacity=47,
                                     watermark_text='测试 123', watermark_size=36, watermark_angle=-32))
        assert dialog.fields['watermark_position'].isEnabled() and not dialog.fields['watermark_density'].isEnabled()
        dialog.fields['watermark_mode'].setCurrentIndex(1)
        assert not dialog.fields['watermark_position'].isEnabled() and dialog.fields['watermark_density'].isEnabled()
        dialog.fields['watermark_mode'].setCurrentIndex(0)
        dialog.commit();app.processEvents()
        assert api.load_config()['watermark_text']=='测试 123' and len(manager.windows)==1
        window = manager.windows[screen]
        assert window.isVisible() and window.focusPolicy()==Qt.NoFocus
        placed = {}
        for position in ('top','bottom','left','right','center'):
            cfg['watermark_position']=position;manager.sync()
            bounds = window.geometry()
            assert screen.availableGeometry().contains(bounds)
            assert bounds == single_geometry(screen.availableGeometry(),window.stamp.size,position)
            placed[position]=bounds.center()
        middle = placed['center']
        assert placed['top'].y()<middle.y()<placed['bottom'].y() and placed['left'].x()<middle.x()<placed['right'].x()
        assert placed['top'].x()==placed['bottom'].x()==middle.x() and placed['left'].y()==placed['right'].y()==middle.y()
        single = window.grab().toImage()
        alpha, x, y = max((single.pixelColor(x,y).alpha(),x,y) for x in range(single.width()) for y in range(single.height()))
        assert abs(alpha-round(255*.47))<=1 and single.pixelColor(0,0).alpha()==0
        assert abs(single.pixelColor(x,y).red()-0x55)<=2 and abs(single.pixelColor(x,y).blue()-0xdd)<=2

        receiver.setGeometry(window.geometry().adjusted(-30,-30,30,30))
        receiver.show();restack(int(receiver.winId()),TOPMOST)
        dialog.hide();app.processEvents()
        user=native()
        user.WindowFromPoint.argtypes=[wintypes.POINT]; user.WindowFromPoint.restype=wintypes.HWND
        focus=user.GetForegroundWindow()
        for layer in ('top','bottom'):
            cfg['watermark_layer']=layer;manager.sync();app.processEvents()
            hwnd=int(window.winId())
            assert is_topmost(hwnd)==(layer=='top')
            if layer=='top':
                assert covers_above(hwnd,int(receiver.winId()))
            flags=user.GetWindowLongW(hwnd,-20)
            assert flags & 0x20 and flags & 0x08000000 and window.testAttribute(Qt.WA_TransparentForMouseEvents)
            rect=wintypes.RECT()
            assert user.GetWindowRect(hwnd,ctypes.byref(rect))
            glyph=wintypes.POINT(rect.left+x*(rect.right-rect.left)//single.width(),
                                 rect.top+y*(rect.bottom-rect.top)//single.height())
            assert user.WindowFromPoint(glyph)==int(receiver.winId()) and user.GetForegroundWindow()==focus
        cfg.update(watermark_mode='tile',watermark_angle=90)
        manager.sync()
        assert set(manager.windows)==set(app.screens()) and window.geometry()==screen.geometry()
        tile_area=QRectF(0,0,1920,1080)
        assert len(list(tile_centers(tile_area, window.stamp.size,10)))>len(list(tile_centers(tile_area,window.stamp.size,1)))
        assert all(w.windowFlags() & Qt.WindowTransparentForInput for w in manager.windows.values())
        assert single_geometry(QRect(-1600,0,1600,900),window.stamp.size,'right').right()<0
        cfg['watermark_opacity']=0;manager.sync()
        assert not manager.windows
        cfg.update(watermark_opacity=47,watermark_text='');manager.sync()
        assert not manager.windows
        cfg['watermark_text']='测试 123'
        with patch.object(runtime.tray,'settings_dialog',dialog,create=True):
            common_actions(menu,runtime.tray)
            toggle=next(a for a in menu.actions() if a.text()=='桌面文字水印')
            assert toggle.isChecked()
            toggle.trigger();quick.refresh()
            assert not cfg['watermark_enabled'] and not quick.tiles['watermark'].active and not manager.windows
            quick.tiles['watermark'].click()
            assert quick.tiles['watermark'].active and api.load_config()['watermark_enabled'] and manager.windows
        checks.append('Watermark: five positions, rotated glyph color/opacity, tile density and display coverage; empty and 0% release surfaces')
        checks.append('Watermark: native hit tests on painted letters pass to the underlying window at both z-orders without focus changes')
        checks.append('Watermark: settings save, tray toggle and Dock tile share display state and saved options')
    finally:
        cfg.update(original);manager.sync();api.save_config(cfg)
        for widget in (quick,menu,dialog,receiver):
            widget.hide();widget.deleteLater()
