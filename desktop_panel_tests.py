"""Desktop collection regression; only used on the verified isolated test desktop."""
import copy
import time
from pathlib import Path
from PyQt5.QtCore import Qt, QEventLoop, QTimer, QMimeData, QPoint, QPointF, QUrl
from PyQt5.QtGui import QDragEnterEvent, QDropEvent
from desktop_catalog import scan_desktop, category
from desktop_panels import DesktopPanels
from app_catalog import path_key
from ui_style import apply_theme


def wait_for(app, predicate, seconds=4):
    deadline = time.monotonic()+seconds
    while not predicate() and time.monotonic() < deadline:
        loop = QEventLoop()
        QTimer.singleShot(20, loop.quit)
        loop.exec_()
    assert predicate(), 'Desktop operation timed out'


def run(api, runtime, root, output, checks):
    from PyQt5.QtWidgets import QApplication
    app, cfg = QApplication.instance(), runtime.dock.cfg
    root, output = Path(root), Path(output)
    desktop = root/'DesktopDemo'
    desktop.mkdir(exist_ok=True)
    fixtures = ['浏览器.url', '项目计划.docx', '预算表.xlsx', '照片.png', '音乐.mp3', '资料.zip', '设备.dat']
    for name in fixtures: (desktop/name).write_text('demo', encoding='utf-8')
    (desktop/'工作资料').mkdir(exist_ok=True)
    (desktop/'工作资料'/'内部文档.txt').write_text('nested', encoding='utf-8')
    (desktop/'desktop.ini').write_text('ignored', encoding='utf-8')
    rows, errors = scan_desktop([str(desktop)])
    assert not errors and len(rows) == 8
    assert {row['panel'] for row in rows} == {'apps','documents','images','media','archives','other','folders'}
    assert not any('内部文档' in row['name'] or row['name'] == 'desktop.ini' for row in rows)
    original_dock = copy.deepcopy(cfg['items'])
    runtime.panels.close()
    cfg['desktop_auto_sort'] = True
    cfg['desktop_panels'] = []
    cfg['desktop_entries'] = []
    cfg['desktop_excluded'] = []
    cfg['panel_auto_hide'] = False
    runtime.panels = manager = DesktopPanels(runtime, roots=[str(desktop)])
    manager.apply_settings()
    manager.scan_timer.stop()
    manager.scan()
    wait_for(app, lambda: manager.worker is None and len(cfg['desktop_entries']) == 8)
    assert len(manager.windows) == 7 and cfg['items'] == original_dock
    assert all(window.isVisible() and not window.windowFlags() & Qt.WindowStaysOnTopHint for window in manager.windows.values())
    compact_id = manager.new_panel('紧凑布局')
    compact = manager.windows[compact_id]
    compact_files = []
    for name in ('logo.png', '人力流程图2026.png', '边牧.png'):
        path = root/name
        path.write_text('compact fixture', encoding='utf-8')
        compact_files.append(str(path))
    manager.add_paths(compact_id, compact_files)
    compact.restoring = True
    compact.resize(260, 300)
    compact.restoring = False
    compact.fit_content()
    app.processEvents()
    assert compact.height() < 220, ('Excess empty space', compact.size())
    assert compact.list.visualItemRect(compact.list.item(2)).bottom() <= compact.list.viewport().height()
    for theme in ('light', 'dark'):
        manager.update_panel(compact_id, theme=theme, opacity=55, color='#8fbfe0')
        app.processEvents()
        compact.grab().save(str(output/('desktop-compact-'+theme+'.png')))
    before_search = compact.height()
    compact.query.setText('不存在的筛选')
    app.processEvents()
    assert compact.height() == before_search
    compact.query.clear()
    many = []
    for index in range(30):
        path = root/('compact-%02d.txt' % index)
        path.write_text('scroll fixture', encoding='utf-8')
        many.append(str(path))
    manager.add_paths(compact_id, many)
    app.processEvents()
    compact.list.doItemsLayout()
    assert compact.height() <= 240 and compact.list.verticalScrollBar().maximum() > 0
    manager.remove_entries({path_key(path) for path in many})
    app.processEvents()
    assert compact.height() < 220
    compact.resize(360, 330)
    compact.store_geometry()
    compact.render()
    app.processEvents()
    assert compact.height() == 330 and manager.model(compact_id)['compact'] is False
    assert api.load_config()['desktop_panels'][-1]['compact'] is False
    compact.set_compact(True)
    app.processEvents()
    assert compact.height() < 220
    compact.collapse()
    assert compact.height() == 44
    compact.expand()
    app.processEvents()
    assert compact.height() < 220 and compact.list.count() == 3
    checks.append('compact panel: three items at 260px width fit without bottom gap, light/dark render, manual resize persists and compact reset/collapse restore')
    custom = manager.new_panel('项目资料')
    target = manager.windows[custom]
    target.move(64, 82)
    target.resize(420, 320)
    target.store_geometry()
    assert manager.model(custom)['geometry'] == [64, 82, 420, 320]
    source = desktop/'项目计划.docx'
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(source)), QUrl.fromLocalFile(str(desktop/'工作资料'))])
    enter = QDragEnterEvent(QPoint(20, 65), Qt.CopyAction | Qt.MoveAction, mime, Qt.LeftButton, Qt.NoModifier)
    target.dragEnterEvent(enter)
    assert enter.isAccepted() and enter.dropAction() == Qt.CopyAction
    drop = QDropEvent(QPointF(20, 65), Qt.CopyAction | Qt.MoveAction, mime, Qt.LeftButton, Qt.NoModifier)
    target.dropEvent(drop)
    assert drop.isAccepted() and len(manager.rows(custom)) == 2 and source.exists()
    # Independent panel sorting and native context-menu pin actions.
    import os
    os.utime(source, (2000000000, 2000000000))
    os.utime(desktop/'工作资料', (1000000000, 1000000000))
    for order, first in [('modified_desc',str(source)), ('modified_asc',str(desktop/'工作资料'))]:
        manager.update_panel(custom, sort=order)
        assert manager.rows(custom)[0]['path'] == first
    manager.update_panel(custom, sort='name_desc')
    assert [row['name'] for row in manager.rows(custom)] == sorted([row['name'] for row in manager.rows(custom)], reverse=True)
    for index in range(target.list.count()):
        target.list.item(index).setSelected(target.list.item(index).data(Qt.UserRole)['path'] == str(source))
    menu = target.build_item_menu()
    assert menu.actions()[0].text() == '置顶'
    menu.actions()[0].trigger()
    assert manager.rows(custom)[0]['path'] == str(source) and manager.rows(custom)[0]['pinned']
    assert api.load_config()['desktop_entries'] == cfg['desktop_entries']
    menu = target.build_item_menu()
    assert menu.actions()[0].text() == '取消置顶'
    menu.actions()[0].trigger()
    assert not next(row for row in manager.rows(custom) if row['path'] == str(source))['pinned']
    manager.update_panel(custom, sort='name_asc')
    assert manager.model(custom)['sort'] == api.load_config()['desktop_panels'][-1]['sort']
    checks.append('panel sorting: name ascending/descending, modification time old/new, real pin/unpin context actions override sort, independent saved order and pin reload')
    manager.scan()
    wait_for(app, lambda: manager.worker is None)
    assert len(manager.rows(custom)) == 2  # Manual assignments survive auto-refresh.
    assert cfg['items'] == original_dock
    target.list.item(0).setSelected(True)
    target.query.setText('不存在的筛选')
    assert not target.selected_keys()
    target.query.clear()
    key = path_key(str(source))
    manager.remove_entries({key})
    manager.scan()
    wait_for(app, lambda: manager.worker is None)
    assert not any(path_key(row['path']) == key for row in cfg['desktop_entries']) and source.exists()
    manager.add_paths(custom, [str(source)])
    manager.update_panel(custom, collapse_style='bar', auto_hide=True)
    target.collapse()
    assert target.isVisible() and target.collapsed and target.height() == 44 and target.width() == 420
    target.move(76, 94)
    target.store_geometry()
    assert manager.model(custom)['geometry'] == [76, 94, 420, 320]
    target.expand()
    assert target.size().width() == 420 and target.size().height() == 320
    manager.update_panel(custom, collapse_style='capsule')
    target.collapse()
    assert target.width() == round(420*cfg['panel_capsule_ratio']/100) and target.height() == 44
    for ratio in (30, 55, 100):
        manager.update_panel(custom, capsule_ratio=ratio)
        assert target.width() == max(180, round(420*ratio/100)) and target.height() == 44
        assert manager.model(custom)['geometry'] == [76, 94, 420, 320]
        assert api.load_config()['desktop_panels'] == cfg['desktop_panels']
        target.grab().save(str(output/('desktop-capsule-ratio-%d.png' % ratio)))
    manager.update_panel(custom, capsule_ratio=70)
    target.expand()
    # Trigger the actual leave/hover timer chains with isolated Qt pointer state.
    import glass_panel
    from PyQt5.QtCore import QEvent
    from types import SimpleNamespace
    original_cursor = glass_panel.QCursor
    glass_panel.QCursor = SimpleNamespace(pos=lambda: QPoint(20000, 20000))
    try:
        target.collapse_timer.setInterval(20)
        target.leaveEvent(QEvent(QEvent.Leave))
        wait_for(app, lambda: target.collapsed)
        assert target.isVisible()
        target.setAttribute(Qt.WA_UnderMouse, True)
        target.expand_timer.setInterval(20)
        target.enterEvent(QEvent(QEvent.Enter))
        wait_for(app, lambda: not target.collapsed)
    finally:
        target.setAttribute(Qt.WA_UnderMouse, False)
        target.collapse_timer.setInterval(650)
        target.expand_timer.setInterval(250)
        glass_panel.QCursor = original_cursor
    manager.update_panel(custom, locked=True, opacity=48, highlight=68, material='liquid')
    assert target.minimumSize() == target.maximumSize() and not target.grip.isVisible()
    size = target.size()
    target.resize(800, 600)
    assert target.size() == size
    manager.update_panel(custom, locked=False)
    assert target.maximumWidth() > target.minimumWidth()
    # Save failure must preserve both the desktop records and Dock list.
    original_save = api.save_config
    previous = copy.deepcopy(cfg['desktop_entries'])
    api.save_config = lambda value: False
    try:
        assert not manager.add_paths('images', [str(source)])
        assert cfg['desktop_entries'] == previous
    finally: api.save_config = original_save
    # QFileSystemWatcher, not polling, discovers new desktop content.
    added = desktop/'新增说明.txt'
    added.write_text('watcher', encoding='utf-8')
    wait_for(app, lambda: any(row['path'] == str(added) for row in cfg['desktop_entries']))
    added.unlink()
    wait_for(app, lambda: not any(row['path'] == str(added) for row in cfg['desktop_entries']))
    for theme in ('light', 'dark'):
        cfg['theme'] = theme
        apply_theme(app, theme == 'light')
        target.apply_options()
        target.expand()
        app.processEvents()
        target.grab().save(str(output/('desktop-panel-'+theme+'.png')))
        target.collapse()
        app.processEvents()
        target.grab().save(str(output/('desktop-capsule-'+theme+'.png')))
        manager.update_panel(custom, collapse_style='bar')
        app.processEvents()
        target.grab().save(str(output/('desktop-bar-'+theme+'.png')))
        manager.update_panel(custom, collapse_style='capsule')
        target.expand()
    # Per-panel presets are staged until save and never alter another panel or Dock.
    from glass_panel import PanelOptions
    from settings_dialog import SettingsDialog
    from appearance_presets import PANEL_PRESETS, DOCK_PRESETS
    dialog = PanelOptions(target)
    dialog.show()
    from ui_style import ThemeSwatches, THEME_COLORS
    swatches = dialog.findChild(ThemeSwatches)
    assert len(swatches.buttons) == 7
    swatches.buttons[3].click()
    assert dialog.color.text() == THEME_COLORS[3][1]
    finished = []
    dialog.finished.connect(finished.append)
    dialog.fields['capsule_ratio'].setValue(55)
    dialog.commit()
    assert dialog.isVisible() and not finished and target.option('capsule_ratio') == 55
    dialog.fields['capsule_ratio'].setValue(100)
    dialog.reject()
    assert target.option('capsule_ratio') == 55
    original_model = copy.deepcopy(manager.model(custom))
    other_models = copy.deepcopy([model for model in cfg['desktop_panels'] if model['id'] != custom])
    dock_values = {key: cfg[key] for key in DOCK_PRESETS[0][1]}
    dialog = PanelOptions(target)
    dialog.preset.setCurrentIndex(2)
    assert manager.model(custom) == original_model
    dialog.reject()
    for index, (name, values) in enumerate(PANEL_PRESETS, 1):
        dialog = PanelOptions(target)
        dialog.preset.setCurrentIndex(index)
        dialog.commit()
        assert all(manager.model(custom)[key] == value for key, value in values.items())
        assert [model for model in cfg['desktop_panels'] if model['id'] != custom] == other_models
        assert {key: cfg[key] for key in dock_values} == dock_values
        app.processEvents()
        target.grab().save(str(output/('panel-preset-%d.png' % index)))
        if name == '全透明':
            assert target.is_clear() and target.backdrop is None
            picture = target.grab().toImage()
            assert picture.pixelColor(round(picture.width()*.8), round(picture.height()*.7)).alpha() == 0
    dialog = PanelOptions(target)
    dialog.color.setText('#badhex')
    dialog.commit()
    assert manager.model(custom)['color'] == PANEL_PRESETS[-1][1]['color']
    dialog.reject()
    for theme in ('light','dark'):
        apply_theme(app, theme == 'light')
        dialog = PanelOptions(target)
        dialog.show()
        app.processEvents()
        dialog.grab().save(str(output/('panel-options-'+theme+'.png')))
        dialog.reject()
    manager.update_panel(custom, **{key:value for key,value in original_model.items() if key != 'id'})
    # Missing overrides must continue to use defaults after restoring this fixture.
    model = manager.model(custom)
    for key in set(model)-set(original_model): del model[key]
    api.save_config(cfg)
    target.apply_options()
    # Dock preset cancellation, save/reload, custom color, and independence.
    original_cfg = copy.deepcopy(cfg)
    settings = SettingsDialog(runtime.tray, api)
    settings.reveal()
    settings.dock_preset.setCurrentIndex(1)
    settings.reject()
    assert cfg == original_cfg
    for index, (name, values) in enumerate(DOCK_PRESETS, 1):
        settings.reveal()
        settings.dock_preset.setCurrentIndex(index)
        settings.commit()
        assert all(cfg[key] == value for key,value in values.items())
        assert cfg['desktop_panels'] == original_cfg['desktop_panels']
        runtime.dock.grab().save(str(output/('dock-preset-%d.png' % index)))
        if name == '全透明':
            assert not runtime.dock.blur_timer.isActive() and runtime.dock.backdrop is None
            from PyQt5.QtGui import QImage, QPainter, QPainterPath
            from PyQt5.QtCore import QRectF
            image = QImage(240, 80, QImage.Format_ARGB32)
            image.fill(Qt.transparent)
            painter = QPainter(image)
            path = QPainterPath()
            rect = QRectF(0, 0, 240, 80)
            path.addRoundedRect(rect, 18, 18)
            colors = runtime.dock.theme_colors()
            runtime.dock._paint_glass_piece(painter, path, rect, rect, colors, 0, runtime.dock.merged_grad_stops(colors))
            painter.end()
            assert all(image.pixelColor(x, y).alpha() == 0 for x in range(240) for y in range(80))
    settings.reveal()
    settings.fields['theme_color'].setText('#c77252')
    settings.commit()
    assert api.load_config()['theme_color'] == '#c77252'
    assert runtime.dock.theme_colors()['tint'] != runtime.dock.base_theme_colors()['tint']
    settings.reveal()
    settings.fields['theme_color'].setText('invalid-color')
    settings.commit()
    assert cfg['theme_color'] == '#c77252'
    settings.reject()
    cfg.update(original_cfg)
    api.save_config(cfg)
    runtime.apply_settings()
    checks.append('appearance presets: five independent panel/Dock schemes including zero-alpha clear background; staged cancel, save/reload and custom colors; no layout, list or other-panel changes')
    # Reload into fresh windows using persisted independent geometry/options/items.
    snapshot = api.load_config()
    assert snapshot['desktop_entries'] == cfg['desktop_entries']
    manager.close()
    cfg.update(snapshot)
    runtime.panels = manager = DesktopPanels(runtime, roots=[str(desktop)])
    manager.apply_settings()
    manager.scan_timer.stop()
    restored = manager.windows[custom]
    assert restored.geometry().getRect() == (76, 94, 420, 320)
    assert restored.option('opacity') == 48 and restored.option('material') == 'liquid'
    assert cfg['items'] == original_dock
    checks.append('desktop panels: seven automatic types, independent Dock list, local-file Copy drops, persistent manual assignment, exclusions, save-failure safety and live directory events')
    checks.append('desktop panels: independent move/resize/lock and reload, persistent bar/capsule collapse, shared Dock glass renderer, light/dark screenshots; originals preserved')
    # A real native SysListView32 on the isolated desktop stands in for Explorer.
    # The injected finder can only return these test-owned windows.
    import ctypes
    from ctypes import wintypes
    from desktop_icons import DesktopIcons
    user = ctypes.windll.user32
    user.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
        wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p]
    user.CreateWindowExW.restype = wintypes.HWND
    user.DestroyWindow.argtypes = [wintypes.HWND]
    class Controls(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('classes', wintypes.DWORD)]
    controls = Controls(ctypes.sizeof(Controls), 1)
    ctypes.windll.comctl32.InitCommonControlsEx(ctypes.byref(controls))
    def create_view():
        handle = user.CreateWindowExW(0x08000080, 'SysListView32', 'Isolated desktop icon fixture',
                    0x90000000, 0, 0, 120, 90, None, None, None, None)
        assert handle
        return handle
    views = [create_view()]
    user.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user.GetWindow.restype = wintypes.HWND
    restored.attach_desktop(views[0])
    assert user.GetWindow(int(restored.winId()), 4) == views[0]  # GW_OWNER
    user.SetWindowLongPtrW(int(restored.winId()), -8, 0)
    visible = lambda handle: bool(user.GetWindowLongW(handle, -16) & 0x10000000)
    journal = root/'visibility-test.json'
    icons = DesktopIcons(finder=lambda: list(views), journal_path=str(journal))
    try:
        icons.set_enabled(True)
        assert not visible(views[0]) and journal.exists()
        icons.set_enabled(False)
        assert visible(views[0]) and not journal.exists()
        user.ShowWindow(views[0], 0)
        icons.set_enabled(True)
        icons.close()
        assert not visible(views[0])  # An originally hidden desktop stays hidden.
        user.ShowWindow(views[0], 4)
        icons.set_enabled(True)
        views.append(create_view())
        wait_for(app, lambda: not visible(views[-1]))
        icons.close()
        assert all(visible(handle) for handle in views)
        icons.set_enabled(True)
        # Leave the durable journal as if the old process had terminated.
        user.UnhookWinEvent(icons.hook)
        icons.hook, icons.enabled = None, False
        icons.hidden.clear()
        icons.journal = None
        recovered = DesktopIcons(finder=lambda: list(views), journal_path=str(journal))
        assert all(visible(handle) for handle in views) and not journal.exists()
        recovered.close()
        blocker = root/'not-a-directory'
        blocker.write_text('block', encoding='utf-8')
        failed = DesktopIcons(finder=lambda: list(views), journal_path=str(blocker/'visibility.json'))
        failed.set_enabled(True)
        assert all(visible(handle) for handle in views)  # No unjournaled hiding.
        failed.close()
    finally:
        icons.close()
        for handle in views: user.DestroyWindow(handle)
    checks.append('desktop icons: native hide/restore, preserve originally-hidden state, real WinEvent handles replacement view, durable recovery journal and save-failure keep-visible path; test-owned HWNDs only')
