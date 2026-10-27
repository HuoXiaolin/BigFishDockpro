"""Feature regression checks, called only from the verified isolated GUI suite."""
import json
import math
from pathlib import Path
from types import SimpleNamespace
from PyQt5.QtCore import Qt, QEventLoop, QTimer
from PyQt5.QtWidgets import QApplication, QWidget
from feature_config import normalize
from runtime_controller import RuntimeController
from ui_style import apply_theme
from update_service import parse_manifest, fetch_manifest
from platform_services import covers_monitor, set_priority, foreground_fullscreen
from app_catalog import path_key


def run(api, dock, tray, root, output, checks):
    app, cfg = QApplication.instance(), dock.cfg
    cfg.update(card_scale=100,settings_size='small');api.save_config(cfg)
    from app_version import VERSION, PROJECT_ID, DISPLAY_NAME, METADATA
    assert VERSION == METADATA['version'] and PROJECT_ID == 'BigFishDockpro' and DISPLAY_NAME == '大肥鱼Dock'
    assert api.APP_NAME == PROJECT_ID and api.APP_TITLE == DISPLAY_NAME and api.COMPAT_NAME == 'BigFishDock'
    root, output = Path(root), Path(output)
    normalized = normalize(dict(cfg, corner_radius=999, startup_delay='broken', panel_material='unknown'))
    assert normalized['corner_radius'] == 120 and normalized['startup_delay'] == 0 and normalized['panel_material'] == 'liquid'
    legacy = normalize(dict(cfg, theme='gloss', panel_theme='gloss'))
    assert legacy['theme'] == legacy['panel_theme'] == 'light'
    assert legacy['dock_material'] == legacy['panel_material'] == 'gloss'
    assert '--autostart' in api.autostart_command()
    checks.append('configuration validation and explicit autostart invocation')
    entries = []
    for n in range(61):
        path = root/('demo-%03d.url' % n)
        path.write_text('[InternetShortcut]\nURL=https://example.com\n', encoding='utf-8')
        entries.append({'path':str(path), 'name':['浏览器', '代码编辑器', '设计文档'][n % 3]+' %02d' % n,
                        'group':['网络', '开发', '办公'][n % 3]})
    cfg['items'] = entries
    assert normalize({})['dock_visible'] and not normalize({})['panel_enabled']
    cfg['panel_enabled'] = True
    cfg['panel_auto_hide'] = False
    cfg['panel_page_size'] = 12
    dock.reload()
    assert dock.page_count > 1 and dock.width() <= app.primaryScreen().availableGeometry().width()
    dock.change_page(1)
    assert dock.page_offset > 0
    original = list(cfg['items'])
    offset = dock.page_offset
    dock.drag_idx = 0
    dock._drag_reorder(dock.rects[1][0]+100)
    assert cfg['items'][offset]['path'] == original[offset+1]['path']
    assert cfg['items'][:offset] == original[:offset]
    items_before = list(cfg['items'])
    next(action for action in dock.icon_context_menu(0).actions() if action.text()=='移除').trigger()
    assert cfg['items'] == items_before[:offset]+items_before[offset+1:]
    assert Path(items_before[offset]['path']).exists()
    cfg['items'] = items_before
    api.save_config(cfg)
    dock.reload()
    checks.append('Dock overflow pages and reorder preserve global item indices')
    dock.show()
    runtime = tray.runtime = RuntimeController(dock, tray, api)
    from desktop_panel_tests import run as run_desktop_panels
    run_desktop_panels(api, runtime, root, output, checks)
    panel = next(iter(runtime.panels.windows.values()))
    cfg['screen_corners'] = True
    cfg['corner_radius'] = 36
    import runtime_controller
    original_detector = runtime_controller.foreground_fullscreen
    cfg['fullscreen_detection'] = False
    runtime_controller.foreground_fullscreen = lambda: False
    runtime.configure_fullscreen_timer()
    assert not runtime.fullscreen_timer.isActive() and runtime.corners.widgets
    runtime_controller.foreground_fullscreen = lambda: True
    runtime.check_fullscreen()
    assert not runtime.game_active
    assert len(runtime.corners.widgets) == 4*len(app.screens())
    app.processEvents()
    for index, mask in enumerate(runtime.corners.widgets):
        geo = app.screens()[index//4].geometry()
        expected_x = geo.right()+1-mask.width() if mask.right else geo.left()
        expected_y = geo.bottom()+1-mask.height() if mask.bottom else geo.top()
        assert mask.geometry().getRect() == (expected_x, expected_y, mask.width(), mask.height()), (
            'Corner moved into work area', mask.geometry().getRect(), expected_x, expected_y)
    corner = runtime.corners.widgets[0]
    runtime.check_fullscreen()
    assert runtime.corners.widgets[0] is corner
    assert corner.windowFlags() & Qt.WindowTransparentForInput
    picture = corner.grab().toImage()
    assert picture.pixelColor(0,0).alpha() > 200
    assert picture.pixelColor(35,35).alpha() == 0
    corner.grab().save(str(output/'screen-corner.png'))
    for mask in runtime.corners.widgets:
        image = mask.grab().toImage()
        edge_x, edge_y = image.width()-1, image.height()-1
        assert image.pixelColor(edge_x if mask.right else 0, edge_y if mask.bottom else 0).alpha() > 200
        assert image.pixelColor(0 if mask.right else edge_x, 0 if mask.bottom else edge_y).alpha() == 0
    # Reproduce a taskbar-like topmost strip covering the lower masks, then
    # exercise the real WinEvent -> Qt single-shot -> native Z-order repair.
    import ctypes
    from ctypes import wintypes
    user = ctypes.windll.user32
    user.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user.GetWindow.restype = wintypes.HWND
    user.GetForegroundWindow.restype = wintypes.HWND
    user.NotifyWinEvent.argtypes = [wintypes.DWORD, wintypes.HWND, wintypes.LONG, wintypes.LONG]
    def above(upper, lower):
        current = user.GetWindow(lower, 3)  # GW_HWNDPREV walks toward the top.
        for _ in range(1024):
            if not current: return False
            if current == upper: return True
            current = user.GetWindow(current, 3)
        raise AssertionError('Unexpected Z-order cycle')
    cover = QWidget(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
                    Qt.WindowDoesNotAcceptFocus)
    cover.setAttribute(Qt.WA_ShowWithoutActivating)
    geo = app.primaryScreen().geometry()
    cover.setGeometry(geo.left(), geo.bottom()-47, geo.width(), 48)
    original_focus = user.GetForegroundWindow()
    try:
        cover.show()
        user.SetWindowPos(int(cover.winId()), -1, 0, 0, 0, 0, 0x213)
        lower = [int(mask.winId()) for mask in runtime.corners.widgets if mask.bottom and
                 mask.geometry().intersects(geo)]
        assert len(lower) == 2
        assert all(not above(handle, int(cover.winId())) for handle in lower), 'Overlap was not reproduced'
        assert len(runtime.corners.hooks) == 4
        user.NotifyWinEvent(3, int(cover.winId()), 0, 0)
        loop = QEventLoop()
        QTimer.singleShot(200, loop.quit)
        loop.exec_()
        assert all(above(handle, int(cover.winId())) for handle in lower), 'Lower corners still covered'
        assert user.GetForegroundWindow() == original_focus
        assert not runtime.corners.raise_timer.isActive(), 'Own reorder events must not cause a loop'
    finally:
        cover.close()
    checks.append('taskbar corners: reproduced topmost overlap, real WinEvent repair restores both lower masks without activation or idle polling; all four alpha geometries verified')
    runtime_controller.foreground_fullscreen = lambda: False
    runtime.check_fullscreen()
    assert runtime.corners.widgets[0] is corner
    checks.append('screen corners: desktop and ordinary fullscreen both visible, no extra polling, stable click-through masks and alpha geometry')
    runtime.set_dock_visible(True)
    runtime.panels.reveal()
    runtime.toggle_game(True)
    assert not dock.isVisible() and not panel.isVisible() and not runtime.corners.widgets
    assert not runtime.corners.hooks and not runtime.corners.raise_timer.isActive()
    runtime.toggle_game(False)
    assert dock.isVisible() and panel.isVisible()
    runtime.set_dock_visible(False)
    runtime.toggle_game(True)
    runtime.toggle_game(False)
    assert not dock.isVisible()
    runtime.set_dock_visible(True)
    assert covers_monitor((0,0,1920,1080),(0,0,1920,1080))
    assert not covers_monitor((0,0,1920,1040),(0,0,1920,1080))
    cfg['fullscreen_detection'] = True
    runtime.configure_fullscreen_timer()
    try:
        runtime_controller.foreground_fullscreen = lambda: True
        runtime.check_fullscreen()
        assert runtime.game_active and not dock.isVisible() and runtime.corners.widgets
        runtime.settings_open = True
        runtime.check_fullscreen()
        assert runtime.corners.widgets and not runtime.game_active
        runtime.settings_closed()
        assert runtime.game_active and runtime.corners.widgets
        runtime_controller.foreground_fullscreen = lambda: False
        runtime.check_fullscreen()
        assert not runtime.game_active and dock.isVisible() and runtime.corners.widgets
        runtime_controller.foreground_fullscreen = lambda: True
        cfg['screen_corners'] = False
        runtime.check_fullscreen()
        assert runtime.game_active and not runtime.corners.widgets
        cfg['screen_corners'] = True
        runtime.set_lite(True)
        runtime.check_fullscreen()
        assert runtime.corners.widgets and not runtime.fullscreen_timer.isActive()
        runtime.toggle_game(True)
        assert not runtime.corners.widgets
        runtime.toggle_game(False)
        assert runtime.corners.widgets
        runtime.set_lite(False)
        assert runtime.corners.widgets and runtime.fullscreen_timer.isActive()
        runtime_controller.foreground_fullscreen = lambda: False
        runtime.check_fullscreen()
    finally:
        runtime_controller.foreground_fullscreen = original_detector
    checks.append('game mode: preserve hidden/visible states, automatic transition, maximized work area excluded')
    # Real window geometry/style APIs on this isolated desktop; only the foreground
    # selector is injected because the test desktop must never receive user input.
    import ctypes
    user = ctypes.windll.user32
    original_foreground = user.GetForegroundWindow
    probe = QWidget()
    try:
        user.GetForegroundWindow = lambda: int(probe.winId())
        probe.resize(300, 200)
        probe.show()
        app.processEvents()
        assert not foreground_fullscreen(exclude_pid=-1)
        probe.showMaximized()
        app.processEvents()
        assert not foreground_fullscreen(exclude_pid=-1)
        probe.showFullScreen()
        app.processEvents()
        assert foreground_fullscreen(exclude_pid=-1)
        assert not foreground_fullscreen()  # Exclude our own windows.
        probe.showNormal()
        app.processEvents()
        assert not foreground_fullscreen(exclude_pid=-1)
    finally:
        user.GetForegroundWindow = original_foreground
        probe.close()
    checks.append('native fullscreen detector: real normal/maximized/fullscreen/restore window geometry on isolated desktop')
    cfg['lite_enabled'] = True
    runtime.settings_open = True
    runtime.arm_lite()
    assert not runtime.lite_timer.isActive()
    runtime.settings_closed()
    assert runtime.lite_timer.isActive() and runtime.lite_timer.interval() == 60000
    # Exercise the real Qt timeout chain with a short test-only interval.
    for timer in (dock.blur_timer, dock.proc_timer, dock.geo_timer):
        timer.start(8000)
    runtime.lite_timer.start(20)
    loop = QEventLoop()
    QTimer.singleShot(70, loop.quit)
    loop.exec_()
    assert runtime.lite and dock.lite_mode
    assert not any(timer.isActive() for timer in (dock.blur_timer,dock.proc_timer,dock.geo_timer,runtime.fullscreen_timer))
    assert panel.isVisible() and panel.collapsed and runtime.corners.widgets and dock.backdrop is None
    assert all(window.list.count()==0 for window in runtime.panels.windows.values())
    dock._proc_busy = True
    dock._apply_running({'test.exe'})
    assert not dock._proc_busy and not dock.running
    runtime.settings_open = True
    runtime.set_lite(False)
    runtime.arm_lite()
    assert not runtime.lite and not runtime.lite_timer.isActive()
    panel.expand()
    assert panel.list.count()==len(panel.visible_items())
    cfg['lite_enabled'] = False
    runtime.settings_closed()
    assert not runtime.lite_timer.isActive()
    checks.append('lightweight: real timeout transition, production 60-second delay, polling stops, settings wake and opt-out')
    result = parse_manifest({'product_id':'BigFishDockpro','version':'9.0.0','release_url':'https://example.com/releases'})
    assert result['newer']
    for payload in ({'product_id':'Upstream','version':'9.0.0'},
                    {'product_id':'BigFishDockpro','version':'9.0.0','release_url':'http://example.com'},
                    {'product_id':'BigFishDockpro','version':'bad'}):
        try:
            parse_manifest(payload)
            raise AssertionError('Invalid update manifest accepted')
        except ValueError:
            pass
    runtime.updater.check()
    assert '尚未配置' in runtime.updater.message and runtime.updater.worker is None
    # Real parsing/proxy path with an in-memory HTTP response, no live source.
    import update_service
    import urllib.request
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def geturl(self): return 'https://example.com/version.json'
        def read(self, limit): return b'{"product_id":"BigFishDockpro","version":"9.0.0"}'
    class Opener:
        def open(self, request, timeout):
            assert timeout == 12
            return Response()
    original_opener = urllib.request.build_opener
    captured = []
    try:
        urllib.request.build_opener = lambda *handlers: (captured.append(handlers) or Opener())
        assert fetch_manifest('https://example.com/version.json', True)['newer']
        assert captured[-1] == ()
        assert fetch_manifest('https://example.com/version.json', False)['newer']
        assert len(captured[-1]) == 1
    finally:
        urllib.request.build_opener = original_opener
    checks.append('updates: own-product/version/HTTPS validation, proxy selection and unconfigured no-network state')
    from update_service import UpdateWorker
    received = []
    worker = UpdateWorker('https://example.com/version.json', False, lambda *_: {'version':'9.0.0'})
    worker.ready.connect(received.append)
    worker.start()
    worker.wait(500)
    app.processEvents()
    assert received == [{'version':'9.0.0'}]
    import threading
    gate = threading.Event()
    cancelled = UpdateWorker('https://example.com/version.json', False, lambda *_: (gate.wait(.3) or {'version':'9.0.0'}))
    cancelled.ready.connect(received.append)
    cancelled.start()
    cancelled.cancelled.set()
    gate.set()
    cancelled.wait(500)
    app.processEvents()
    assert received == [{'version':'9.0.0'}]
    checks.append('update worker: asynchronous signal delivery and cancellation suppress late callbacks')
    from startup_tests import run as check_startup
    check_startup(api, tray, root, checks)
    tray.rebuild()
    assert len([action for action in tray.menu.actions() if not action.isSeparator()]) <= 8
    for theme in ('light','dark'):
        apply_theme(app, theme == 'light')
        settings = tray.settings_dialog if hasattr(tray,'settings_dialog') else None
        if settings is None:
            from settings_dialog import SettingsDialog
            fake = SimpleNamespace(**dict(api.__dict__,CONFIG_DIR=r'C:\Users\Demo\AppData\Roaming\BigFishDock'))
            settings = tray.settings_dialog = SettingsDialog(tray,fake)
        settings.reveal()
        from appearance_presets import MATERIALS, COLOR_MODES
        for left,right,options in [('dock_material','panel_material',MATERIALS), ('theme','panel_theme',COLOR_MODES)]:
            for key in (left,right):
                field=settings.fields[key]
                assert [(field.itemText(i),field.itemData(i)) for i in range(field.count())] == options
        assert not settings.windowIcon().isNull()
        assert settings.windowIcon().cacheKey() == app.windowIcon().cacheKey()
        from ui_style import ThemeSwatches, THEME_COLORS
        swatches = settings.findChildren(ThemeSwatches)
        assert len(swatches) == 2
        previous_colors = [widget.buttons[0].field.text() for widget in swatches]
        for widget in swatches:
            for button, (_, color) in zip(widget.buttons, THEME_COLORS):
                button.click()
                assert button.field.text() == color
        # Palette clicks are staged; reopening discards unsaved choices.
        settings.reject()
        settings.reveal()
        assert [widget.buttons[0].field.text() for widget in swatches] == previous_colors
        assert settings.windowFlags() & Qt.FramelessWindowHint
        finished = []
        settings.finished.connect(finished.append)
        runtime.settings_open = True
        runtime.arm_lite()
        settings.fields['theme'].setCurrentIndex(settings.fields['theme'].findData(theme))
        settings.commit()
        assert settings.isVisible() and not finished and runtime.settings_open
        assert not runtime.lite_timer.isActive() and '已保存' in settings.status.text()
        settings.header.minimize.click()
        app.processEvents()
        assert settings.isMinimized() and not finished
        settings.reveal()
        app.processEvents()
        assert not settings.isMinimized() and settings.isVisible()
        from ui_style import ModernSpinBox, ModernComboBox, ModernCheckBox
        from PyQt5.QtWidgets import QSpinBox, QComboBox, QCheckBox
        assert all(isinstance(field, ModernSpinBox) for field in settings.findChildren(QSpinBox))
        assert all(isinstance(field, ModernComboBox) for field in settings.findChildren(QComboBox))
        assert all(isinstance(field, ModernCheckBox) for field in settings.findChildren(QCheckBox))
        spin = settings.fields['dock_highlight']
        original_value = spin.value()
        spin.plus.click()
        assert spin.value() == original_value+1
        spin.minus.click()
        assert spin.value() == original_value
        for index in range(settings.tabs.count()):
            settings.tabs.setCurrentIndex(index)
            assert settings.tabs.pages.currentIndex() == settings.tabs.nav.currentRow() == index
            app.processEvents()
            settings.grab().save(str(output/('feature-settings-%s-%d.png' % (theme,index))))
            scroll = settings.tabs.pages.widget(index)
            scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
            app.processEvents()
            settings.grab().save(str(output/('feature-settings-%s-%d-bottom.png' % (theme,index))))
            scroll.verticalScrollBar().setValue(0)
        settings.resize(640, 480)
        settings.tabs.setCurrentIndex(0)
        app.processEvents()
        settings.grab().save(str(output/('settings-compact-'+theme+'.png')))
        settings.resize(800, 640)
        settings.header.close.click()
        assert not settings.isVisible() and finished
        settings.finished.disconnect(finished.append)
        runtime.settings_closed()
    from panel_group_tests import run as run_group_tests
    run_group_tests(api, runtime, root, output, checks)
    from material_tests import run as run_material_tests
    run_material_tests(api,runtime,output,checks)
    from config_transfer_tests import run as run_transfer_tests
    run_transfer_tests(api,runtime,root,output,checks)
    from running_apps_tests import run as run_running_tests
    run_running_tests(api,runtime,root,output,checks)
    from external_launch_tests import run as run_external_tests
    run_external_tests(api,runtime,root,output,checks)
    from desktop_visibility_tests import run as run_visibility_tests
    run_visibility_tests(api,runtime,root,output,checks)
    from sticky_notes_tests import run as run_notes_tests
    run_notes_tests(api,runtime,root,output,checks)
    # Fresh default geometry, reopen and theme changes must not accumulate scaling.
    from settings_dialog import SettingsDialog
    from ui_style import compact_dialog
    from PyQt5.QtCore import QPoint, QSize
    dense=SettingsDialog(runtime.tray,api)
    try:
        assert dense.size()==QSize(560,448), dense.size()
        dense.reveal();app.processEvents()
        assert dense.width()<=570 and dense.height()<=458, dense.size()
        original_size=dense.size()
        for theme in ('light','dark'):
            apply_theme(app,theme=='light');compact_dialog(dense);app.processEvents()
            assert dense.size()==original_size,(theme,dense.size(),original_size)
            for number in range(dense.tabs.count()):
                dense.tabs.setCurrentIndex(number);app.processEvents()
                scroll=dense.tabs.pages.currentWidget()
                for edge in (0,scroll.verticalScrollBar().maximum()):
                    scroll.verticalScrollBar().setValue(edge);app.processEvents()
                dense.grab().save(str(output/('settings-density-%s-%d.png'%(theme,number))))
            assert dense.save.width()>=dense.save.fontMetrics().horizontalAdvance(dense.save.text())+8
            spin=dense.fields['dock_highlight']
            dense.tabs.setCurrentIndex(0);app.processEvents()
            assert spin.plus.geometry().right()<spin.width() and spin.minus.geometry().left()>0
            assert not spin.plus.geometry().intersects(spin.minus.geometry())
            runtime.tray.rebuild();menu=runtime.tray.menu
            menu.popup(QPoint(40,40));app.processEvents()
            assert menu.width()<=190 and menu.height()<=230,menu.size()
            for action in menu.actions():
                if action.isSeparator():continue
                assert menu.actionGeometry(action).height()>=menu.fontMetrics().height()+4
                assert menu.fontMetrics().horizontalAdvance(action.text())+40<=menu.width(),action.text()
                if action.menu():
                    submenu=action.menu();submenu.popup(QPoint(250,40));app.processEvents()
                    assert submenu.width()<=300
                    submenu.hide()
            menu.grab().save(str(output/('menu-density-'+theme+'.png')));menu.hide()
        dense.reject();dense.reveal();app.processEvents()
        assert dense.size()==original_size
        assert runtime.dock.cfg['icon_size']==api.load_config()['icon_size']
        checks.append('compact interface: default settings 560x448 (49 percent former area), all six pages in both themes, menu/submenu text and row hitboxes, spin button separation, save text, reopen/theme idempotence; Dock/card configuration unchanged')
    finally:
        dense.reject();runtime.updater.changed.disconnect(dense.update_changed);dense.deleteLater()
        apply_theme(app,runtime.dock.is_light())
    from card_sizing_tests import run as run_sizing_tests
    run_sizing_tests(api,runtime,root,output,checks)
    from screen_layout_tests import run as run_layout_tests
    run_layout_tests(api,runtime,root,output,checks)
    runtime.close()
    app.aboutToQuit.disconnect(runtime.close)
    checks.append('settings: save stays open without finished or lite countdown; minimize/restore and close controls; compact and default layouts, all pages in both themes')
