"""Idle reclamation must preserve visible pixels and bound repeated resource use."""
import copy,json,ctypes
from datetime import datetime
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class SnapshotTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 11, 9, 14, 35, 18, tzinfo=tz)

def private_bytes():
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in ('peak_ws','ws','peak_pool_paged','pool_paged','peak_pool_nonpaged','pool_nonpaged','pagefile','peak_pagefile','private')]
    counters=Counters();counters.cb=ctypes.sizeof(counters)
    kernel=ctypes.WinDLL('kernel32');kernel.GetCurrentProcess.restype=wintypes.HANDLE
    psapi=ctypes.WinDLL('psapi');psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(counters),counters.cb):raise ctypes.WinError()
    return counters.private


def check_idle_reclaim(runtime):
    from PyQt5 import sip
    from PyQt5.QtCore import QCoreApplication, QDate, QEvent
    from PyQt5.QtGui import QCursor
    from PyQt5.QtWidgets import QApplication
    from resource_options import background

    app = QApplication.instance()
    service = runtime.resources
    budget = runtime.memory_budget
    cfg = runtime.dock.cfg
    appearance = dict(background(cfg), material='liquid')
    with patch.dict(cfg, resource_enabled=True, resource_collapsed=False, resource_auto_hide=False,
                    resource_ai=True, resource_weather=True, resource_weather_cities=['天津', '沈阳'],
                    resource_component_locations={}, resource_background='custom',
                    resource_appearance=appearance, resource_face=True, resource_face_interactive=True,
                    motion_enabled=True):
        service.sync()
        window = service.window
        window.select_page('resources')
        dashboard = window.dashboard
        window.select_page('ai')
        ai = window.ai_view
        details = ai.detail_dialog
        date = QDate.currentDate().addDays(-12)
        ai.start.setDate(date)
        window.select_page('weather')
        window.weather_view.city.setCurrentText('沈阳')
        window.weather_view.remarks_button.setChecked(True)
        weather = window._weather_view
        geometry = window.geometry()
        window.grab()
        glass_key = window.glass.image.cacheKey()
        budget.last_release = time.monotonic() - 61
        with patch.object(QCursor, 'pos', return_value=budget.cursor), patch('memory_budget.private_resident', return_value=32*2**20):
            with patch.object(runtime, 'ui_busy', return_value=True):
                budget.check()
                assert window._ai_view is ai
            with patch.object(runtime, 'ui_busy', return_value=False):
                budget.check()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        assert window._ai_view is None and window.dashboard is None
        assert sip.isdeleted(details) and sip.isdeleted(dashboard)
        assert window._weather_view is weather and window.page_key == 'weather' and window.geometry() == geometry
        assert window.liquid.watch.isActive() and window.glass.image.cacheKey() == glass_key
        assert all(panel.isVisible() for panel in runtime.panels.windows.values())

        window.select_page('ai')
        reopened = window.ai_view
        reopened.ensure_details()
        assert reopened.start.date() == date
        assert budget.reclaim(trim_caches=False) and window._weather_view is None
        window.select_page('weather')
        assert window.weather_view.city.currentText() == '沈阳' and window.weather_view.remarks_button.isChecked()
    service.sync()


def run(api,runtime,output,checks):
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtGui import QPixmap,QColor
    from PyQt5.QtCore import QCoreApplication,QEvent,QTimer
    from glass_capture import backdrop_key
    app=QApplication.instance();dock=runtime.dock;cfg=dock.cfg
    # Isolate reclamation from independent blinking and cursor animation in the pixel comparison.
    face_interactive = cfg['panel_face_interactive']
    cfg.update(panel_enabled=True,panels_visible=True,clock_enabled=True,calendar_enabled=True,notes_enabled=True,notes_visible=True,game_mode=False,fullscreen_detection=False,panel_face_interactive=False)
    runtime.apply_settings();dock.show()
    with patch.object(dock,'start_backdrop') as prepare:
        dock.hide();dock.show();assert prepare.called
    panels=[w for w in runtime.panels.windows.values() if w.isVisible()]
    assert panels
    for panel in panels:
        with patch.object(panel,'capture_backdrop') as prepare:
            panel.hide();panel.show();assert prepare.called
            for collapsed in (True,False):
                prepare.reset_mock();panel.set_collapsed_geometry(collapsed);assert prepare.called
    checks.append('Dock/card reopen and card fold/unfold prepare wallpaper synchronously before the next frame')
    identity=runtime.notes.new();note=runtime.notes.windows[identity]
    surfaces=[dock,runtime.clock,runtime.calendar,note]+[w for w in runtime.panels.windows.values() if w.isVisible()]
    for window in surfaces:
        window.backdrop=QPixmap(window.size());window.backdrop.fill(QColor('#9bcce8'))
    for _ in range(4):app.processEvents()
    # Minute rollover or a running clock hand is independent of idle reclamation.
    clock_time = SimpleNamespace(datetime=SnapshotTime)
    with patch('dock_extras.datetime', clock_time), patch('desktop_clock.datetime', clock_time):
        before=[(w.geometry(),w.backdrop.cacheKey(),w.grab().toImage()) for w in surfaces]
        assert runtime.memory_budget.reclaim(trim_caches=False)
        for w,(geometry,key,image) in zip(surfaces,before):
            assert w.geometry()==geometry and w.backdrop.cacheKey()==key
            assert w.grab().toImage()==image,w.__class__.__name__
    cfg['panel_face_interactive'] = face_interactive
    runtime.apply_settings({'panel_face_interactive'})
    checks.append('idle reclamation preserves exact rendered Dock/card/note/clock/calendar pixels, geometry and backdrop')
    # Wallpaper/key caching is measured with a synthetic capture, not user data.
    calls=[]
    dock.preview=False;cfg.update(glass=True,clear_background=False,dock_material='liquid')
    with patch('glass_capture.backdrop_key',return_value=('fixed',)),patch.object(dock,'_capture_behind',side_effect=lambda:(calls.append(True) or surfaces[0].backdrop,True)):
        dock._backdrop_key=None
        for _ in range(10):dock.refresh_backdrop()
        assert len(calls)==1
    dock.preview=True
    def cycle():
        QTimer.singleShot(0,lambda:app.activeModalWidget().reject())
        runtime.open_card_sizing()
        runtime.memory_budget.reclaim()
    for _ in range(4):cycle()
    QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    baseline=private_bytes();children=len(dock.findChildren(__import__('PyQt5.QtCore',fromlist=['QObject']).QObject))
    samples=[];windows=len(app.topLevelWidgets())
    for _ in range(20):
        cycle()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        samples.append(private_bytes())
    assert len(dock.findChildren(__import__('PyQt5.QtCore',fromlist=['QObject']).QObject))<=children+2
    assert len(app.topLevelWidgets())<=windows+2
    assert max(samples)-baseline<16*1024*1024,(baseline,samples)
    (Path(output)/'idle-memory.json').write_text(json.dumps(dict(baseline_private_bytes=baseline,final_private_bytes=samples[-1],peak_private_bytes=max(samples),cycles=20,limits='short local synthetic scenario, not long-duration user workload'),indent=2),encoding='utf-8')
    checks.append('unchanged wallpaper blurs once across ten refreshes; 20 settings and cleanup cycles retain bounded QObject count and private memory')
    check_idle_reclaim(runtime)
    checks.append('normal idle check reclaims hidden windows and capsule pages below the cache trim threshold, waits for menus, restores AI dates and weather city, and retains the active page, glass and face follow')
