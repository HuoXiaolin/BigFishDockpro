"""Exercise actual Windows tray callback windows and their tracking tooltips."""
import ctypes
from ctypes import wintypes as wt
from datetime import datetime, timedelta
from tempfile import TemporaryDirectory
from time import monotonic
from unittest.mock import patch

from PyQt5.QtCore import QPoint, QRect, QEventLoop, Qt, QTimer
from PyQt5.QtGui import QPalette


def run(service, app, output, checks):
    from bluetooth_gauge import devices
    from resource_quota_day import QuotaDayHistory
    from run_isolated_test import assert_isolated
    from tray_readout import TRAY_MESSAGE, WM_MOUSEMOVE, NIN_POPUPOPEN, _logical_point
    from PyQt5.QtWidgets import QSystemTrayIcon

    assert_isolated()
    user = ctypes.WinDLL('user32')
    user.SendMessageW.argtypes = (wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
    user.SendMessageW.restype = wt.LPARAM
    user.IsWindowVisible.argtypes = (wt.HWND,)
    user.GetWindowRect.argtypes = (wt.HWND, ctypes.POINTER(wt.RECT))
    user.GetClientRect.argtypes = (wt.HWND, ctypes.POINTER(wt.RECT))
    options = dict(resource_bt_tray=True, resource_ai_tray=True, resource_ai_tray_mode='fixed',
                   resource_ai_tray_provider='Codex', resource_ai_tray_metric='week',
                   resource_tray_runner_enabled=True, resource_tray_runner_animal='penguin',
                   resource_tray_runner_metric='cpu', resource_tray_runner_speed='fixed_high', resource_tray_runner_device='')
    saved = {key: service.cfg[key] for key in options}
    palette = app.palette()

    def wait_for(condition):
        deadline = monotonic() + 2.5
        while not condition() and monotonic() < deadline:
            loop = QEventLoop()
            QTimer.singleShot(20, loop.quit)
            loop.exec_()
        assert condition()

    def visible(tray):
        return bool(tray.popup and tray.popup.isVisible() and user.IsWindowVisible(int(tray.popup.winId())))

    def lines(tray):
        return tray.popup.document.toPlainText().splitlines()

    def screenshot(tray, name):
        rect = wt.RECT()
        hwnd = int(tray.popup.winId())
        assert user.GetWindowRect(hwnd, ctypes.byref(rect)) and rect.bottom - rect.top >= 36
        client = wt.RECT()
        assert user.GetClientRect(hwnd, ctypes.byref(client))
        assert (client.right, client.bottom) == (rect.right - rect.left, rect.bottom - rect.top)
        app.processEvents()
        picture = app.primaryScreen().grabWindow(hwnd)
        assert not picture.isNull() and picture.save(str(output / ('tray-hover-' + name + '.png')))
        image = picture.toImage()
        pixels = [image.pixel(x, y) & 0xffffff for y in range(3, image.height()-3) for x in range(3, image.width()-3)]
        assert pixels.count(0xffffff) > len(pixels) // 2 and pixels.count(0) >= 12, name
        assert all(image.pixel(x, y) & 0xffffff == 0xffffff
                   for x in range(image.width()) for y in (0, image.height()-1)), name
        assert all(image.pixel(x, y) & 0xffffff == 0xffffff
                   for y in range(image.height()) for x in (0, image.width()-1)), name

    try:
        assert service.set_options(**options)
        bt = service.bluetooth
        bt.tray.show()  # Preview normally suppresses registering this icon.
        pet = service.runners['tray']
        ai = service.ai_tray.tray
        ai.show()
        slots = {bt.tray.hwnd: QRect(100, 200, 24, 24), pet.tray.hwnd: QRect(124, 200, 24, 24),
                 ai.hwnd: QRect(148, 200, 24, 24)}
        assert None not in slots and len(slots) == 3
        names = ['蓝牙耳机', '无线键盘', '旅行鼠标', '电量笔']
        raw = [dict(id=f'{n:012X}', name=name, level=v)
               for n, (name, v) in enumerate(zip(names, [72, 0, None, 49]), 1)]
        bt.publish(devices(raw), '')
        with patch('tray_readout._pointer') as pointer, patch('tray_readout._icon_rect', side_effect=slots.get), \
                patch('resource_runner.uptime_minutes', return_value=1443), patch.object(service, 'runner_reading', return_value=47):
            def hover(tray):
                pointer.return_value = slots[tray.hwnd].center()
                user.SendMessageW(tray.hwnd, TRAY_MESSAGE, 0, WM_MOUSEMOVE)

            assert QSystemTrayIcon.toolTip(bt.tray)==''
            pointer.return_value=QPoint(1,205)
            for message in (WM_MOUSEMOVE,NIN_POPUPOPEN):
                user.SendMessageW(bt.tray.hwnd,TRAY_MESSAGE,slots[bt.tray.hwnd].center().x() | (211<<16),message)
            assert bt.tray.anchor is None and not bt.tray.delay.isActive() and not visible(bt.tray)
            hover(bt.tray)
            wait_for(lambda: visible(bt.tray))
            assert bt.tray.popup.anchor==_logical_point(pointer.return_value)
            assert lines(bt.tray) == ['外设电量', '蓝牙耳机  72%', '无线键盘  0%', '旅行鼠标  未报告', '第 1/2 组']
            screenshot(bt.tray, 'bluetooth')
            handle = bt.tray.popup
            bt.publish(devices([dict(row, name=row['name'] + '·Bluetooth' * 6) for row in raw]), '')
            assert len(bt.tray.readout) > 127 and lines(bt.tray) == bt.tray.readout.splitlines()
            bt.publish(devices(raw), '')
            bt.turn_tray()
            assert visible(bt.tray) and bt.tray.popup == handle and lines(bt.tray) == ['外设电量', '电量笔  49%', '第 2/2 组']
            dark = QPalette(palette)
            dark.setColor(QPalette.ToolTipBase, Qt.black)
            dark.setColor(QPalette.Text, Qt.white)
            dark.setColor(QPalette.ToolTipText, Qt.white)
            app.setPalette(dark)
            pet.update_reading()
            hover(pet.tray)
            wait_for(lambda: visible(pet.tray))
            assert not visible(bt.tray)
            assert lines(pet.tray) == ['小企鹅', 'CPU 47%', '本次开机时长　1 天 0 小时 3 分钟']
            screenshot(pet.tray, 'animal')
            handle, frame = pet.tray.popup, pet.frame
            wait_for(lambda: pet.frame != frame)
            assert visible(pet.tray) and pet.tray.popup == handle
            with patch.object(service, 'runner_reading', return_value=0):
                pet.update_reading()
                assert visible(pet.tray) and lines(pet.tray)[1] == 'CPU 0%'
            user.SendMessageW(pet.tray.hwnd, TRAY_MESSAGE, 0, 0x0400)  # NIN_SELECT
            assert visible(pet.tray) and pet.tray.popup == handle
            pointer.return_value = QPoint(80, 100)
            wait_for(lambda: not visible(pet.tray))
            assert pet.tray.toolTip() == pet.readout
            assert QSystemTrayIcon.toolTip(pet.tray)==''
            hover(bt.tray)
            pointer.return_value = QPoint(80, 100)
            wait_for(lambda: not bt.tray.delay.isActive())
            assert not visible(bt.tray)
            hover(bt.tray)
            wait_for(lambda: visible(bt.tray))
            bt_popup = int(bt.tray.popup.winId())
            assert service.set_options(resource_bt_tray=False)
            assert not user.IsWindowVisible(bt_popup)
            now = datetime.now().astimezone()
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            metric = dict(label='每周额度', kind='percent', window=10080, reset=(now + timedelta(days=6, minutes=10)).isoformat())
            provider = dict(id='Codex', name='Codex', plan='prolite', quotaAt=now.isoformat(),
                            quotaDayStart=dict(at=start.isoformat(), plan='prolite', quotas=[dict(metric, percent=3)]),
                            quotas=[dict(metric, percent=43)])
            # The shared runtime may already contain a newer sample for this plan.
            # Give this fixture its own daily history, including its midnight baseline.
            with TemporaryDirectory() as directory, patch.object(service.deck, 'quota_history', QuotaDayHistory(directory)):
                service.deck.accept(dict(type='ai', providers=[provider]))
            hover(ai)
            wait_for(lambda: visible(ai))
            quota_lines = lines(ai)
            assert quota_lines[:3] == ['Codex Pro 100', '周额度剩余 57%', '6 天后恢复'] and '40%' in quota_lines[3], quota_lines
            screenshot(ai, 'quota')
            ai.hide()
            ai.show()
            assert ai.hwnd and not ai.popup and ai.toolTip() == ai.readout
        from taskbar_readout import TaskbarReadout
        from PyQt5.QtCore import QEvent
        from PyQt5.QtGui import QHelpEvent
        strip=TaskbarReadout(service)
        try:
            strip.setGeometry(180,180,250,36);strip.show();app.processEvents()
            strip.setToolTip('CPU  20%\n内存  40%')
            local=strip.rect().center();point=strip.mapToGlobal(local)
            with patch('taskbar_readout.QCursor.pos',return_value=point):
                app.sendEvent(strip,QHelpEvent(QEvent.ToolTip,local,point))
                assert strip.readout_popup.isVisible() and strip.readout_popup.anchor==point
                app.sendEvent(strip,QEvent(QEvent.Leave))
                assert not strip.readout_popup.isVisible()
            with patch('taskbar_readout.QCursor.pos',return_value=QPoint(0,0)):
                app.sendEvent(strip,QHelpEvent(QEvent.ToolTip,local,point))
                assert not strip.readout_popup.isVisible()
        finally:strip.dispose()
        checks.append('Stale tray moves and deferred taskbar help events outside their data target cannot show a popup; accepted events anchor the white readout at the validated point.')
        checks.append('Native mouse-only tray callbacks: Bluetooth device groups, zero/unknown/long names, animal metrics and uptime at 96 fps, click, data refresh, leaving and icon disposal on the isolated desktop.')
        checks.append('Window captures for peripheral battery, animal and AI quota have white backgrounds, black text, separate data lines, and white pixels along all four unframed edges.')
    finally:
        app.setPalette(palette)
        service.set_options(**saved)
