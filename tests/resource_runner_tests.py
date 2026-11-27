"""Exercise both independent pet settings on the real Qt surfaces."""
import copy
import time
from unittest.mock import patch


def visible_on_edge(tile, inset):
    far = tile.width() - 1 - inset
    for pos in range(inset, far + 1):
        if any(tile.pixel(x, y) >> 24 for x, y in
               ((inset, pos), (far, pos), (pos, inset), (pos, far))):
            return True
    return False


def check_coat(animal, image):
    pixels = [image.pixelColor(x, y).getRgb() for y in range(image.height()) for x in range(image.width())]
    assert any(a == 0 for _, _, _, a in pixels)
    fur = [(r, g, b) for r, g, b, a in pixels if a >= 185]
    if animal in ('cat', 'dog'):
        assert any(min(r, g, b) >= 230 and max(r, g, b) - min(r, g, b) < 17 for r, g, b in fur)
        assert any(max(r, g, b) < 99 for r, g, b in fur)
        has_ginger = any(r >= 145 and r - g > 43 and g - b > 28 for r, g, b in fur)
        assert has_ginger == (animal == 'cat')
    elif animal=='rabbit':
        assert any(104 < r < 193 and 2 <= r - g <= 35 and 0 <= g - b <= 25 for r, g, b in fur)
        assert any(r >= 173 and 33 <= r - g <= 106 and 5 <= g - b <= 52 for r, g, b in fur)
    elif animal=='bird':
        assert any(b>r+35 and g>r+25 for r,g,b in fur)
        assert any(r>185 and g>145 and b<130 for r,g,b in fur)
    elif animal=='penguin':
        assert any(b>r and max(r,g,b)<100 for r,g,b in fur)
        assert any(min(r,g,b)>185 for r,g,b in fur)


def check_penguin_waddle():
    from resource_runner import frame_count, sprite, tray_frame

    def center_x(points):
        assert points
        return sum(x for x, y in points) / len(points)

    def center_y(points):
        assert points
        return sum(y for x, y in points) / len(points)

    count = frame_count('penguin')
    assert count == 48
    for size in (16, 20, 24, 32):
        capsule = [sprite('penguin', i, size).toImage() for i in range(count)]
        tray = [tray_frame('penguin', i).pixmap(size, size).toImage() for i in range(count)]
        for frames in (capsule, tray):
            side = frames[0].width()
            head = frames[0].copy(0, 0, side, round(.44 * side))
            bill = [(x, y) for y in range(head.height()) for x in range(side)
                    for r, g, b, a in [head.pixelColor(x, y).getRgb()]
                    if a >= 65 and r > 86 and r - g > 25 and g - b > 24]
            assert center_x(bill) > .69 * side
            belly_edges, soles = [], []
            for im in frames:
                assert im.copy(head.rect()) == head, (size, 'moving head')
                row = round(.80 * (side - 1))
                cream = [x for x in range(side) for r, g, b, a in [im.pixelColor(x, row).getRgb()]
                         if a > 185 and min(r, g, b) > 156 and r > b]
                belly_edges.append(max(cream))
                soles.append(max(y for y in range(side) for x in range(side) if im.pixel(x, y) >> 24 >= 64))
            assert max(belly_edges) - min(belly_edges) <= 1 and max(soles) - min(soles) <= 1

    near_feet, far_feet, near_wings, far_wings = {}, {}, {}, {}
    for i in (0, 12, 18, 24, 36):
        im = sprite('penguin', i, 128).toImage()
        points = [(x, y, *im.pixelColor(x, y).getRgb()) for y in range(64, 128) for x in range(128)]
        shoes = [(x, y, r) for x, y, r, g, b, a in points if y >= 103 and a > 225 and r - g > 64 and g - b > 60]
        near_feet[i] = [(x, y) for x, y, r in shoes if r >= 240]
        far_feet[i] = [(x, y) for x, y, r in shoes if 195 <= r <= 228]
        if i in (0, 24):
            near_wings[i] = [(x, y) for x, y, r, g, b, a in points if y < 108 and a > 215
                             and 80 < r < 200 and r <= b < r + 40 and abs(r - g) < 8]
            far_wings[i] = [(x, y) for x, y, r, g, b, a in points if y < 110 and a > 205
                            and 14 < r < 100 and g >= r + 6 and b > g + 10]
        if i in (0, 12, 24, 36):
            # The light breast remains visible from the side, even when the
            # nearer flipper crosses the flank. Its outline must stay fixed.
            contour = tuple(max(x for x, y, r, g, b, a in points if y == row and a > 200
                                and min(r, g, b) > 156 and r > b) for row in (88, 96, 101, 104, 106))
            if i == 0:
                reference = contour
            else:
                assert contour == reference
    assert center_x(near_feet[0]) > center_x(far_feet[0]) + 8
    assert center_x(near_feet[24]) + 12 < center_x(far_feet[24])
    assert abs(center_y(near_feet[0]) - center_y(near_feet[12])) < 1.5
    assert center_y(near_feet[36]) < center_y(near_feet[12]) - 4
    assert max(y for x, y in far_feet[18] if x >= 64) < max(y for x, y in far_feet[24] if x >= 64)
    # At near-foot contact the near flipper trails and the far one leads.
    # After the opposite contact their fore/aft order has reversed.
    assert center_x(near_wings[0]) + 7 < center_x(near_wings[24])
    assert center_x(far_wings[0]) > center_x(near_wings[0]) + 28
    assert center_x(far_wings[24]) + 24 < center_x(near_wings[24])


def check_shared_pace(capsule, tray, service):
    from resource_runner import FRAMES, frame_rate

    original = [(pet.animal, pet.speed, pet.metric, pet.device) for pet in (capsule, tray)]
    try:
        with patch.object(service, 'runner_reading') as reading, patch('resource_runner.perf_counter') as clock:
            for mode, load, other in (('fixed_low', 0, 'cat'), ('fixed_medium', 0, 'dog'),
                                      ('fixed_high', 0, 'bird'), ('adaptive', 1, 'rabbit'),
                                      ('adaptive', 5, 'cat'), ('adaptive', 25, 'dog'),
                                      ('adaptive', 50, 'bird'), ('adaptive', 100, 'rabbit')):
                penguin, reference = (tray, capsule) if other in ('cat', 'bird') else (capsule, tray)
                start = clock.return_value = 100.
                reading.return_value = load
                for pet, animal in ((penguin, 'penguin'), (reference, other)):
                    pet.configure('dog' if animal == 'cat' else 'cat', mode, 'cpu')
                    pet.configure(animal, mode, 'cpu')
                rate = frame_rate(mode, load)
                assert penguin.fps == reference.fps == rate
                if mode == 'adaptive' and load <= 5:
                    assert 0 < penguin.timer.interval() < reference.timer.interval()
                    clock.return_value = start + .55 / rate
                    penguin.advance()
                    reference.advance()
                    assert 0 < penguin.frame < 6 and reference.frame == 0
                # Check two whole cycles, then skip several deadlines in one wake-up.
                for tick in (*range(1, 2 * FRAMES + 1), 37):
                    clock.return_value = start + (tick + .00001) / rate
                    reference.advance()
                    penguin.advance()
                    assert reference.frame == tick % FRAMES
                    assert penguin.frame == 6 * reference.frame
                if mode == 'adaptive' and load == 5:
                    clock.return_value += .4 / rate
                    reading.return_value = 50
                    for pet in (penguin, reference):
                        pet.update_reading()
                    assert abs(penguin.next_frame - reference.next_frame) < 1e-7
                    clock.return_value = max(penguin.next_frame, reference.next_frame) + 1e-7
                    for pet in (penguin, reference):
                        pet.advance()
                    assert penguin.frame == 6 * reference.frame == 36
                    for idle in (0, None):
                        reading.return_value = idle
                        for pet in (penguin, reference):
                            pet.update_reading()
                            assert not pet.timer.isActive()
                        clock.return_value += 2
                        penguin.advance()
                        reference.advance()
                        assert penguin.frame == 6 * reference.frame == 36
                    reading.return_value = 10
                    for pet in (penguin, reference):
                        pet.update_reading()
                    clock.return_value = max(penguin.next_frame, reference.next_frame) + 1e-7
                    penguin.advance()
                    reference.advance()
                    assert penguin.frame == 6 * reference.frame == 42
    finally:
        for pet, options in zip((capsule, tray), original):
            pet.configure(*options)


def run(api, runtime, app, output, checks):
    from PyQt5.QtCore import QEvent, QEventLoop, QPointF, QRect, QTimer, Qt
    from PyQt5.QtGui import QHelpEvent, QImage, QMouseEvent
    from PyQt5.QtWidgets import QSystemTrayIcon,QToolTip
    from config_transfer import normalize as import_config
    from resource_compact import plan
    from resource_options import RUNNER_ANIMALS, RUNNER_METRICS, RUNNER_SLOT, RUNNER_SPEEDS
    from resource_devices import Device, device_key
    from resource_metrics import busiest_disk, disk_loads, gpu_loads, network_device_readings, network_utilization
    from resource_runner import ASSETS, FRAMES, capsule_rect, frame_count, frame_rate, sprite, tray_frame, uptime_minutes, uptime_text
    from resource_settings import ResourceOptions
    from settings_catalog import TASKBAR

    service = runtime.resources
    cfg = service.cfg
    before, auto = copy.deepcopy(cfg), service.auto_compact
    before_hardware, before_times = dict(service.hardware), dict(service.hardware_times)
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
        taskbar = action(action(tray.contextMenu(), '系统外观').menu(), '任务栏').menu()
        return action(taskbar, '托盘小动物').menu()

    assert isinstance(uptime_minutes(),int) and uptime_minutes()>=0
    assert [uptime_text(v) for v in (None,0,1,60,1440)]==['暂不可用','不足 1 分钟','1 分钟','1 小时 0 分钟','1 天 0 小时 0 分钟']
    boot=patch('resource_runner.uptime_minutes',return_value=2*1440+3*60+4)
    boot.start()
    uptime='\n本次开机时长　2 天 3 小时 4 分钟'
    try:
        cfg.update(resource_runner_enabled=False, resource_runner_animal='cat', resource_runner_speed='adaptive',resource_runner_metric='cpu',
                   resource_tray_runner_enabled=False, resource_tray_runner_animal='cat', resource_tray_runner_speed='adaptive',resource_tray_runner_metric='cpu',
                   resource_runner_device='', resource_tray_runner_device='', resource_gpu_device='', resource_network_device='', resource_disk_device='',
                   resource_enabled=False, resource_taskbar=False,
                   resource_capsule_taskbar=False, resource_cpu=False, resource_collapsed=True,
                   resource_auto_hide=False, resource_fold='pill', resource_clock=True)
        service.auto_compact = None
        service.sync()
        assert not service.runners and 'cpu' not in service.needs()
        old = copy.deepcopy(cfg)
        for key in ('resource_runner_enabled', 'resource_tray_runner_enabled', 'resource_tray_runner_animal', 'resource_tray_runner_speed','resource_tray_runner_metric','resource_runner_metric'):
            old.pop(key)
        for place, speed, expected in (('tray','high','fixed_medium'), ('capsule','medium','fixed_low'),
                                       ('off','low','fixed_low'), ('tray','cpu','adaptive')):
            old.update(resource_runner_placement=place, resource_runner_animal='dog', resource_runner_color='black', resource_runner_speed=speed)
            assert api.save_config(old) is not False
            for updated in (api.load_config(), import_config(old, api)):
                assert updated['resource_runner_enabled'] == (place == 'capsule')
                assert updated['resource_tray_runner_enabled'] == (place == 'tray')
                prefix = 'resource_tray_runner_' if place == 'tray' else 'resource_runner_'
                assert updated[prefix + 'animal'] == 'dog' and updated[prefix + 'speed'] == expected
                assert updated[prefix + 'metric'] == 'cpu'
                assert 'resource_runner_placement' not in updated and 'resource_runner_color' not in updated
                assert api.normalize_features(updated) == updated
        previous = dict(cfg, resource_runner_speed='fixed_140ms', resource_tray_runner_speed='fixed_50ms')
        assert api.save_config(previous) is not False
        from layout_profiles import clean_snapshot
        for migrated in (api.load_config(), import_config(previous, api), clean_snapshot({'values':previous})['values']):
            assert (migrated['resource_runner_speed'], migrated['resource_tray_runner_speed']) == ('fixed_low','fixed_high')
        assert import_config(dict(previous,resource_tray_runner_speed='fixed_80ms'),api)['resource_tray_runner_speed']=='fixed_medium'
        assert api.save_config(cfg) is not False

        dialog = ResourceOptions(service)
        dialog.tabs.setCurrentIndex(2)
        assert not dialog.fields['resource_runner_animal'].isEnabled()
        assert not dialog.fields['resource_runner_metric'].isEnabled()
        assert all('tray_runner' not in key and key != 'resource_runner_color' for page in dialog.field_pages for key in page)
        field = dialog.fields['resource_runner_speed']
        assert [field.itemData(i) for i in range(field.count())] == list(RUNNER_SPEEDS)
        dialog.fields['resource_runner_enabled'].setChecked(True)
        choose(dialog.fields['resource_runner_animal'], 'rabbit')
        choose(dialog.fields['resource_runner_metric'], 'memory')
        choose(field, 'fixed_low')
        dialog.tabs.setCurrentIndex(0)
        assert dialog.commit()
        dialog.reject()
        saved = api.load_config()
        assert saved['resource_runner_enabled'] and saved['resource_runner_animal'] == 'rabbit'
        assert saved['resource_runner_metric']=='memory'
        assert saved['resource_runner_speed'] == 'fixed_low' and not saved['resource_tray_runner_enabled']

        tray.show_settings()
        main = tray.settings_dialog
        main.tabs.setCurrentIndex(TASKBAR)
        assert 'resource_runner_enabled' not in main.catalog and not main.fields['resource_tray_runner_speed'].isEnabled()
        main.fields['resource_tray_runner_enabled'].setChecked(True)
        choose(main.fields['resource_tray_runner_animal'], 'dog')
        choose(main.fields['resource_tray_runner_speed'], 'fixed_high')
        main.save.click()
        saved = api.load_config()
        assert saved['resource_tray_runner_enabled'] and saved['resource_tray_runner_animal'] == 'dog'
        assert saved['resource_tray_runner_speed'] == 'fixed_high' and saved['resource_runner_animal'] == 'rabbit'
        runner = service.runners['tray']
        assert service.window is None and runner.tray.isVisible() and runner.fps == 96
        assert runner.tray.contextMenu() is tray.contextMenu()
        menu = pet_menu()
        assert action(menu, '显示托盘小动物').isChecked()
        assert action(action(menu, '动物形象').menu(), '小狗').isChecked()
        action(action(menu, '奔跑速度').menu(), RUNNER_SPEEDS['adaptive']).trigger()
        assert main.fields['resource_tray_runner_speed'].currentData() == 'adaptive'
        assert action(action(menu,'监测指标').menu(),'CPU').isChecked()
        main.reject()
        assert 'cpu' in service.active_keys()
        speeds = []
        for load in (0, 25, 50, 75, 100):
            service.accept_sample(dict(time=time.monotonic(), cpu=load))
            speeds.append(runner.fps)
            assert runner.timer.isActive() == (load > 0)
            assert runner.tray.toolTip()==f'小狗\nCPU {load}%'+uptime
            if load==50:
                # No pointer is available for keyboard activation on the private
                # desktop. The mouse activation path is exercised with the tray HWND.
                with patch('tray_readout._pointer', return_value=None):
                    with patch.object(runner.tray,'geometry',return_value=QRect()),patch.object(QToolTip,'showText') as show:
                        runner.tray.activated.emit(QSystemTrayIcon.Trigger)
                        show.assert_not_called()
                        assert runner.tray.toolTip()=='小狗\nCPU 50%'+uptime
                        with patch('resource_runner.uptime_minutes',return_value=2*1440+3*60+5):
                            runner.tray.activated.emit(QSystemTrayIcon.Trigger)
                            assert runner.tray.toolTip().endswith('3 小时 5 分钟')
                QToolTip.hideText()
        assert speeds == [0, 24, 48, 72, 96], speeds
        assert [frame_rate('adaptive', load) for load in (-1, None, float('nan'), 120)] == [0, 0, 0, 96]
        current = runner.frame
        service.accept_sample(dict(time=time.monotonic(), cpu=0))
        runner.advance()
        assert runner.frame == current and not runner.timer.isActive()
        service.accept_sample(dict(time=time.monotonic(), cpu=.00000001))
        assert 0 < runner.fps < 1 and runner.timer.interval() <= 2_147_483_647
        for key,label in RUNNER_METRICS.items():
            action(action(pet_menu(),'监测指标').menu(),label).trigger()
            assert key in service.active_keys() and api.load_config()['resource_tray_runner_metric']==key
            now=time.monotonic()
            service.accept_sample({'time':now,key:(50.,100,200) if key=='memory' else 50.})
            assert runner.fps==48 and runner.tray.toolTip()==f'小狗\n{label} 50%'+uptime
            service.accept_sample({'time':now+20,key:None})
            assert runner.fps==0 and not runner.timer.isActive() and runner.tray.toolTip()==f'小狗\n{label} —'+uptime
        for mode, fps in (('fixed_low',24), ('fixed_medium',48), ('fixed_high',96)):
            menu = pet_menu()
            action(action(menu, '奔跑速度').menu(), RUNNER_SPEEDS[mode]).trigger()
            service.accept_sample(dict(time=time.monotonic(),network_utilization=27))
            assert runner.fps == fps and runner.tray.toolTip()=='小狗\n网络 27%'+uptime
        # Replay Qt's integer-millisecond wake-ups. Rounding every frame to
        # 10 ms would finish all 96 updates 40 ms early.
        first_deadline = runner.next_frame
        wake = first_deadline
        first_frame = runner.frame
        with patch('resource_runner.perf_counter') as clock:
            for _ in range(96):
                clock.return_value = wake
                runner.advance()
                wake += runner.timer.interval() / 1000
            assert abs(wake - first_deadline - 1) < .0011 and runner.frame == first_frame
            clock.return_value = runner.next_frame + 4.25 / runner.fps
            runner.advance()
            assert runner.frame == (first_frame + 5) % FRAMES
        now = time.perf_counter()
        runner.next_frame = now + 1 / runner.fps
        runner.schedule_frame(now)
        action(action(pet_menu(), '动物形象').menu(), '小猫').trigger()
        assert runner.animal == 'cat' and api.load_config()['resource_runner_animal'] == 'rabbit'
        for animal in RUNNER_ANIMALS:
            sheet = QImage(str(ASSETS / (animal + '.png'))).convertToFormat(QImage.Format_ARGB32_Premultiplied)
            columns, rows = (8, 6) if animal == 'penguin' else (4, 2)
            assert (sheet.width(), sheet.height()) == (columns * 128, rows * 128)
            assert frame_count(animal) == columns * rows
            inset = int(sheet.text('TrayInset'))
            assert 0 <= inset < 64
            fills_slot = False
            frames = set()
            for frame in range(frame_count(animal)):
                tile = sheet.copy(frame % columns * 128, frame // columns * 128, 128, 128)
                assert not any(visible_on_edge(tile, i) for i in range(inset)), (animal, frame)
                fills_slot |= visible_on_edge(tile, inset)
                tray_tile = tile.copy(tile.rect().adjusted(inset, inset, -inset, -inset))
                if animal == 'cat':
                    assert sum(tile.pixel(x, y) == 0xffffffff for x in range(0, 128, 2)
                               for y in range(0, 128, 2)) >= 20, frame
                for size in (16, 20, 24, 32):
                    image = sprite(animal, frame, size).toImage()
                    expected = tile.scaled(size, size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                    assert image == expected, (animal, frame, size, image.format(), expected.format(), image.devicePixelRatio())
                    tray_image = tray_frame(animal, frame).pixmap(size, size).toImage()
                    physical = tray_image.width()
                    tray_image.setDevicePixelRatio(1)
                    tray_expected = tray_tile.scaled(physical, physical, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                    assert tray_image == tray_expected, (animal, frame, size, physical, tray_image.format(), tray_expected.format())
                    check_coat(animal, image)
                    check_coat(animal, tray_image)
                frames.add(image.constBits().asstring(image.byteCount()))
            assert len(frames) == frame_count(animal) and fills_slot
        check_penguin_waddle()
        checks.append('48 right-facing poses at 16/20/24/32 px on both Qt surfaces: head pixels and breast outline stay fixed while the two flippers swing in opposition to one another and to the stepping feet.')
        cfg.update(resource_enabled=True)
        service.sync()
        window = service.window
        capsule = service.runners['capsule']
        assert capsule.tray is None and capsule.animal == 'rabbit' and capsule.fps == 24
        assert runner.fps == 96 and runner.animal == 'cat'
        assert service.set_options(resource_runner_animal='penguin', resource_tray_runner_animal='penguin')
        assert capsule.animal == runner.animal == 'penguin'
        check_shared_pace(capsule, runner, service)
        assert service.set_options(resource_runner_animal='rabbit', resource_tray_runner_animal='cat')
        checks.append('Penguin cycle timing matches the other pets on both surfaces at every fixed tier and at 1/5/25/50/100 percent load, including skipped deadlines, load changes, pause and resume.')
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
        cfg['resource_runner_speed'] = 'adaptive'
        service.sync()
        service.accept_sample(dict(time=time.monotonic(), memory=(50,1,2),network_utilization=36))
        assert capsule.fps == 48 and runner.fps == 96
        assert capsule.readout=='小兔 内存 50%'+uptime and runner.tray.toolTip()=='小猫\n网络 36%'+uptime
        for form in ('pill', 'bar', 'ball'):
            cfg['resource_fold'] = form
            service.sync()
            app.processEvents()
            rect = capsule_rect(window)
            window.grab()
            local=rect.center();global_pos=window.mapToGlobal(local)
            app.sendEvent(window,QHelpEvent(QEvent.ToolTip,local,global_pos))
            assert QToolTip.text()==capsule.readout
            for kind,buttons in ((QEvent.MouseButtonPress,Qt.LeftButton),(QEvent.MouseButtonRelease,Qt.NoButton)):
                app.sendEvent(window,QMouseEvent(kind,QPointF(local),QPointF(global_pos),Qt.LeftButton,buttons,Qt.NoModifier))
            assert service.compact and QToolTip.text()==capsule.readout
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
            with patch('resource_runner.perf_counter',return_value=capsule.next_frame):
                capsule.advance()
            assert capsule.frame == (previous + 1) % FRAMES and cache is window._compact_surface
        service.fold(False, automatic=True)
        assert list(service.runners) == ['tray'] and runner.timer.isActive() and 'network_utilization' in service.needs()
        service.fold(True, automatic=True)
        assert 'capsule' in service.runners and 'memory' in service.needs()
        action(pet_menu(), '显示托盘小动物').trigger()
        assert list(service.runners) == ['capsule'] and service.runners['capsule'].timer.isActive()
        assert not action(pet_menu(), '显示托盘小动物').isChecked()
        saved = api.load_config()
        assert saved['resource_runner_enabled'] and not saved['resource_tray_runner_enabled']
        assert saved['resource_tray_runner_animal'] == 'cat' and saved['resource_tray_runner_speed'] == 'fixed_high'
        cfg['resource_runner_enabled'] = False
        service.sync()
        assert not service.runners and 'cpu' not in service.needs()
        assert 'network_utilization' not in service.active_keys()
        checks.append('Running cat, dog and rabbit: independent 24/48/96 fps tiers, 0/24/48/72/96 fps at 0/25/50/75/100 percent, zero stops the timer and tiny positive loads keep a precise deadline.')
        checks.append('Capsule and tray animals show Windows boot uptime on hover and click, including a minute rollover, multi-day uptime and an unavailable utilization reading.')
        checks.append('Five utilization sources: independent saved capsule/tray metrics, real Qt tooltip and mouse-click paths, measured percentages in fixed speed mode, absent data and demand release.')
        assert busiest_disk({'0 C:':80,'1 D:':12,'_Total':0})==88 and busiest_disk({'0':100})==0
        assert busiest_disk({'0':float('nan'),'_Total':20}) is None
        base={1:((1000,8000),(2000,4000)),2:((1200,8000),(1500,8000))}
        sample={1:((1400,8000),(2500,4000)),2:((1800,8000),(2100,8000))}
        assert network_utilization(base,sample,2)==50
        assert network_utilization(base,base,1)==0 and network_utilization({},sample,2) is None
        assert network_utilization(base,{1:((0,8000),(2500,8000))},1) is None
        assert network_utilization(base,{1:((9000,8000),(9999,4000))},1)==100
        assert network_device_readings(base,sample,2)=={1:((200,250),50),2:((300,300),30)}
        assert disk_loads({'0 C:':80,'1 D:':12,'_Total':0})=={0:20,1:88}
        assert gpu_loads({'luid_0x1_0x2_phys_0_eng_0':10,'luid_0x1_0x2_phys_0_eng_1':38,
                          'luid_0x1_0x3_phys_0_eng_0':116})=={0x100000002:38,0x100000003:100}
        checks.append('Disk activity excludes the aggregate instance. Network load uses negotiated per-direction rates and rejects counter resets, new links and speed changes.')
        checks.append('Both Qt surfaces render every source pose, including all 48 penguin drawings. Transparent bounds, coats, tray cropping and cycle wraparound are verified.')

        from resource_panel import display_values
        from taskbar_readout import columns
        gpu_a, gpu_b = (device_key('gpu', x) for x in ('first', 'second'))
        disk = device_key('disk', 'second')
        net = 'net:' + '05' * 16
        display_a, display_b = (device_key('display', x) for x in ('first', 'second'))
        service.update_hardware({'gpu': {gpu_a:Device('GPU A',13),gpu_b:Device('GPU B',21)},
                                 'disk_activity': {disk:Device('磁盘 1',1)},
                                 'network_utilization': {net:Device('以太网',20)},
                                 'display': {display_a:Device('第一屏',r'\\.\DISPLAY1'),display_b:Device('第二屏',r'\\.\DISPLAY2')}})
        dialog.deleteLater()
        dialog = ResourceOptions(service)
        dialog.tabs.setCurrentIndex(2)
        dialog.fields['resource_runner_enabled'].setChecked(True)
        choose(dialog.fields['resource_runner_metric'], 'gpu')
        choose(dialog.fields['resource_runner_device'], gpu_b)
        dialog.tabs.setCurrentIndex(5)
        for key,value in (('gpu',gpu_a),('network',net),('disk',disk),('display',display_b)):
            choose(dialog.fields[f'resource_{key}_device'], value)
        dialog.fields['resource_disk_activity'].setChecked(True)
        dialog.tabs.setCurrentIndex(2)
        assert dialog.fields['resource_runner_device'].currentData() == gpu_b
        assert dialog.commit()
        assert service.set_options(resource_tray_runner_enabled=True,resource_tray_runner_metric='network_utilization',
                                   resource_tray_runner_speed='adaptive',resource_gpu=True,resource_network=True,
                                   resource_fold='pill',resource_collapsed=True,
                                   resource_compact_metrics=['gpu','network','disk_activity'],resource_task_metrics=['gpu','network','disk_activity'])
        main = None
        menu = pet_menu()
        submenu = action(menu,'监测设备').menu()
        submenu.aboutToShow.emit()
        action(submenu,'以太网').trigger()
        stored = api.load_config()
        assert stored['resource_gpu_device'] == gpu_a and stored['resource_runner_device'] == gpu_b
        assert stored['resource_tray_runner_device'] == net and stored['resource_display_device'] == display_b
        assert import_config(stored,api)['resource_disk_device'] == disk
        from layout_profiles import snapshot
        assert clean_snapshot(snapshot(stored))['values']['resource_display_device'] == display_b
        now = time.monotonic()
        common = {'time':now,'gpu':99,'disk_activity':88,'network':(8000,16000),'network_utilization':90}
        service.accept_sample(dict(common,gpu_devices={gpu_a:15,gpu_b:75},disk_devices={disk:34},
                                   network_devices={net:((1024,2048),25)}))
        assert service.latest['gpu'] == 15 and service.history[-1]['gpu'] == 15
        assert service.latest['disk_activity'] == 34 and service.latest['network'] == (1024,2048)
        assert service.runners['capsule'].fps == 72 and service.runners['tray'].fps == 24
        assert [r[2] for r in display_values(service,False) if r[0]=='disk_activity'] == ['34%']
        speed = next(pair for pair in columns(service) if pair[0] and pair[0][2] == 'network')
        assert (speed[0][1],speed[1][1]) == ('2K/s','1K/s')
        service.accept_sample(common)
        assert not {'gpu','network','disk_activity'} & service.latest.keys()
        assert all(runner.fps == 0 and not runner.timer.isActive() for runner in service.runners.values())
        assert service.set_options(resource_gpu_device='',resource_network_device='',resource_disk_device='')
        assert all(not {'gpu','network'} & row.keys() for row in service.history)
        service.accept_sample(common)
        assert (service.latest['gpu'],service.latest['disk_activity'],service.latest['network']) == (99,88,(8000,16000))
        assert all(runner.fps == 0 for runner in service.runners.values())
        checks.append('Hardware sources: shared GPU/disk/NIC monitor, independent capsule/tray metrics, device dropdowns and tray menu, settings and layout persistence, missing devices and source-specific chart history.')
    finally:
        boot.stop()
        if main is not None and main.isVisible():main.reject()
        if dialog is not None:dialog.deleteLater()
        cfg.clear()
        cfg.update(before)
        service.hardware = before_hardware
        service.hardware_times = before_times
        service.auto_compact = auto
        service.sync()
        api.save_config(cfg)
