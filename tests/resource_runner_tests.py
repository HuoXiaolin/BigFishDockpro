"""Exercise both independent pet settings on the real Qt surfaces."""
import copy
import time


def run(api, runtime, app, output, checks):
    from PyQt5.QtCore import QEventLoop, QRect, QTimer, Qt
    from PyQt5.QtGui import QImage
    from config_transfer import normalize as import_config
    from resource_compact import plan
    from resource_options import RUNNER_ANIMALS, RUNNER_SLOT, RUNNER_SPEEDS
    from resource_runner import ASSETS, FRAMES, FIXED_INTERVALS, capsule_rect, sprite, tray_frame
    from resource_settings import ResourceOptions
    from settings_catalog import TASKBAR

    service = runtime.resources
    cfg = service.cfg
    before, auto = copy.deepcopy(cfg), service.auto_compact
    dialog = main = None
    tray = runtime.tray

    def choose(field, value):
        idx = field.findData(value)
        assert idx >= 0, value
        field.setCurrentIndex(idx)

    def action(menu, title):
        return next(item for item in menu.actions() if item.text() == title)

    def pet_menu():
        tray.rebuild()
        taskbar = action(tray.contextMenu(), '任务栏').menu()
        return action(taskbar, '托盘小动物').menu()

    try:
        cfg.update(resource_runner_enabled=False, resource_runner_animal='cat', resource_runner_speed='cpu',
                   resource_tray_runner_enabled=False, resource_tray_runner_animal='cat', resource_tray_runner_speed='cpu',
                   resource_enabled=False, resource_taskbar=False,
                   resource_capsule_taskbar=False, resource_cpu=False, resource_collapsed=True,
                   resource_auto_hide=False, resource_fold='pill', resource_clock=True)
        service.auto_compact = None
        service.sync()
        assert not service.runners and 'cpu' not in service.needs()
        old = copy.deepcopy(cfg)
        for key in ('resource_runner_enabled', 'resource_tray_runner_enabled', 'resource_tray_runner_animal', 'resource_tray_runner_speed'):
            old.pop(key)
        for place, speed, expected in (('tray','high','fixed_80ms'), ('capsule','medium','fixed_140ms'),
                                       ('off','low','fixed_140ms'), ('tray','cpu','cpu')):
            old.update(resource_runner_placement=place, resource_runner_animal='dog', resource_runner_color='black', resource_runner_speed=speed)
            assert api.save_config(old) is not False
            for updated in (api.load_config(), import_config(old, api)):
                assert updated['resource_runner_enabled'] == (place == 'capsule')
                assert updated['resource_tray_runner_enabled'] == (place == 'tray')
                prefix = 'resource_tray_runner_' if place == 'tray' else 'resource_runner_'
                assert updated[prefix + 'animal'] == 'dog' and updated[prefix + 'speed'] == expected
                assert 'resource_runner_placement' not in updated and 'resource_runner_color' not in updated
                assert api.normalize_features(updated) == updated
        assert api.save_config(cfg) is not False

        dialog = ResourceOptions(service)
        dialog.tabs.setCurrentIndex(2)
        assert not dialog.fields['resource_runner_animal'].isEnabled()
        assert all('tray_runner' not in key and key != 'resource_runner_color' for page in dialog.field_pages for key in page)
        field = dialog.fields['resource_runner_speed']
        assert [field.itemData(i) for i in range(field.count())] == list(RUNNER_SPEEDS)
        dialog.fields['resource_runner_enabled'].setChecked(True)
        choose(dialog.fields['resource_runner_animal'], 'rabbit')
        choose(field, 'fixed_140ms')
        dialog.tabs.setCurrentIndex(0)
        assert dialog.commit()
        dialog.reject()
        saved = api.load_config()
        assert saved['resource_runner_enabled'] and saved['resource_runner_animal'] == 'rabbit'
        assert saved['resource_runner_speed'] == 'fixed_140ms' and not saved['resource_tray_runner_enabled']

        tray.show_settings()
        main = tray.settings_dialog
        main.tabs.setCurrentIndex(TASKBAR)
        assert 'resource_runner_enabled' not in main.catalog and not main.fields['resource_tray_runner_speed'].isEnabled()
        main.fields['resource_tray_runner_enabled'].setChecked(True)
        choose(main.fields['resource_tray_runner_animal'], 'dog')
        choose(main.fields['resource_tray_runner_speed'], 'fixed_50ms')
        main.save.click()
        saved = api.load_config()
        assert saved['resource_tray_runner_enabled'] and saved['resource_tray_runner_animal'] == 'dog'
        assert saved['resource_tray_runner_speed'] == 'fixed_50ms' and saved['resource_runner_animal'] == 'rabbit'
        runner = service.runners['tray']
        assert service.window is None and runner.tray.isVisible() and runner.timer.interval() == 50
        assert runner.tray.contextMenu() is tray.contextMenu()
        menu = pet_menu()
        assert action(menu, '显示托盘小动物').isChecked()
        assert action(action(menu, '动物形象').menu(), '小狗').isChecked()
        action(action(menu, '奔跑速度').menu(), RUNNER_SPEEDS['cpu']).trigger()
        assert main.fields['resource_tray_runner_speed'].currentData() == 'cpu'
        main.reject()
        assert 'cpu' in service.active_keys()
        speeds = []
        for load in (0, 25, 50, 75, 100):
            service.accept_sample(dict(time=time.monotonic(), cpu=load))
            speeds.append(runner.timer.interval())
        assert speeds == [300, 171, 120, 92, 75], speeds
        assert list(FIXED_INTERVALS.values()) == [140, 80, 50]
        for mode, interval in FIXED_INTERVALS.items():
            menu = pet_menu()
            action(action(menu, '奔跑速度').menu(), RUNNER_SPEEDS[mode]).trigger()
            assert runner.timer.interval() == interval and 'cpu' not in service.needs()
        action(action(pet_menu(), '动物形象').menu(), '小猫').trigger()
        assert runner.animal == 'cat' and api.load_config()['resource_runner_animal'] == 'rabbit'
        for animal in RUNNER_ANIMALS:
            sheet = QImage(str(ASSETS / (animal + '.png'))).convertToFormat(QImage.Format_ARGB32_Premultiplied)
            assert sheet.width() == 512 and sheet.height() == 256
            frames = set()
            for frame in range(FRAMES):
                tile = sheet.copy(frame % 4 * 128, frame // 4 * 128, 128, 128)
                for size in (16, 24):
                    image = sprite(animal, frame, size).toImage()
                    expected = tile.scaled(size, size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                    assert image == expected, (animal, frame, size, image.format(), expected.format(), image.devicePixelRatio())
                    tray_image = tray_frame(animal, frame).pixmap(size, size).toImage()
                    physical = tray_image.width()
                    tray_image.setDevicePixelRatio(1)
                    tray_expected = tile.scaled(physical, physical, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                    assert tray_image == tray_expected, (animal, frame, size, physical, tray_image.format(), tray_expected.format())
                    colors = [image.pixelColor(x, y) for y in range(size) for x in range(size)]
                    assert any(c.alpha() == 0 for c in colors)
                    assert any(c.alpha() >= 200 and c.lightness() < 75 for c in colors)
                    assert any(c.alpha() >= 200 and c.lightness() > 195 for c in colors)
                frames.add(image.constBits().asstring(image.byteCount()))
            assert len(frames) == 8
        cfg.update(resource_enabled=True)
        service.sync()
        window = service.window
        capsule = service.runners['capsule']
        assert capsule.tray is None and capsule.animal == 'rabbit' and capsule.timer.interval() == 140
        assert runner.timer.interval() == 50 and runner.animal == 'cat'
        ticks = set()
        loop = QEventLoop()
        def tick(slot):
            ticks.add(slot)
            if len(ticks) == 2:
                loop.quit()
        def slow_tick(): tick('capsule')
        def fast_tick(): tick('tray')
        capsule.timer.timeout.connect(slow_tick)
        runner.timer.timeout.connect(fast_tick)
        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(loop.quit)
        timeout.start(1500)
        loop.exec_()
        timeout.stop()
        capsule.timer.timeout.disconnect(slow_tick)
        runner.timer.timeout.disconnect(fast_tick)
        assert ticks == {'capsule', 'tray'}
        cfg['resource_runner_speed'] = 'cpu'
        service.sync()
        service.accept_sample(dict(time=time.monotonic(), cpu=50))
        assert capsule.timer.interval() == 120 and runner.timer.interval() == 50
        for form in ('pill', 'bar', 'ball'):
            cfg['resource_fold'] = form
            service.sync()
            app.processEvents()
            rect = capsule_rect(window)
            window.grab()
            assert window.rect().contains(rect) and rect.center().x() > window.width() / 2
            width = window.taskbar_width({'rect': QRect(0, 0, 1600, 28)})
            assert width == (24 + RUNNER_SLOT if form == 'ball' else cfg['resource_compact_width'])
            assert window.taskbar_width({'rect': QRect(0, 0, 28, 900)}) == 24
            if form == 'ball':
                assert window.width() > window.height()
            else:
                assert plan(window, window.width())['runner_width'] == RUNNER_SLOT
                for hit in [*window.compact_bounds, *window.reminder_bounds, *window.status_bounds.values()]:
                    assert hit.right() <= rect.left(), (form, hit, rect)
            previous = capsule.frame
            cache = window._compact_surface
            capsule.advance()
            assert capsule.frame == (previous + 1) % FRAMES and cache is window._compact_surface
        service.fold(False, automatic=True)
        assert list(service.runners) == ['tray'] and runner.timer.isActive() and 'cpu' not in service.needs()
        service.fold(True, automatic=True)
        assert 'capsule' in service.runners and 'cpu' in service.needs()
        action(pet_menu(), '显示托盘小动物').trigger()
        assert list(service.runners) == ['capsule'] and service.runners['capsule'].timer.isActive()
        assert not action(pet_menu(), '显示托盘小动物').isChecked()
        saved = api.load_config()
        assert saved['resource_runner_enabled'] and not saved['resource_tray_runner_enabled']
        assert saved['resource_tray_runner_animal'] == 'cat' and saved['resource_tray_runner_speed'] == 'fixed_50ms'
        cfg['resource_runner_enabled'] = False
        service.sync()
        assert not service.runners and 'cpu' not in service.needs()
        checks.append('Running cat, dog and rabbit: independent capsule and taskbar settings, live tray context menu and saved readback, simultaneous timers, fold/disable isolation, legacy load/import, five CPU loads and 140/80/50 ms fixed speeds.')
        checks.append('Runner artwork: every 16/24 px tray and capsule frame matches the approved original-color tile, including the dark coat, light markings and transparent surround.')
    finally:
        if main is not None and main.isVisible():main.reject()
        if dialog is not None:dialog.deleteLater()
        cfg.clear()
        cfg.update(before)
        service.auto_compact = auto
        service.sync()
        api.save_config(cfg)
