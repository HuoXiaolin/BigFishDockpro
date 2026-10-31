"""Resource mode must preserve visible pixels and bound repeated resource use."""
import copy,json,ctypes
from pathlib import Path
from unittest.mock import patch

def private_bytes():
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in ('peak_ws','ws','peak_pool_paged','pool_paged','peak_pool_nonpaged','pool_nonpaged','pagefile','peak_pagefile','private')]
    counters=Counters();counters.cb=ctypes.sizeof(counters)
    kernel=ctypes.WinDLL('kernel32');kernel.GetCurrentProcess.restype=wintypes.HANDLE
    psapi=ctypes.WinDLL('psapi');psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(counters),counters.cb):raise ctypes.WinError()
    return counters.private

def run(api,runtime,output,checks):
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtGui import QPixmap,QColor
    from PyQt5.QtCore import QCoreApplication,QEvent,QTimer
    from glass_capture import backdrop_key
    app=QApplication.instance();dock=runtime.dock;cfg=dock.cfg
    cfg.update(lite_enabled=True,panel_enabled=True,panels_visible=True,clock_enabled=True,calendar_enabled=True,notes_enabled=True,notes_visible=True,game_mode=False,fullscreen_detection=False)
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
    before=[(w.geometry(),w.backdrop.cacheKey(),w.grab().toImage()) for w in surfaces]
    assert runtime.set_lite(True)
    for w,(geometry,key,image) in zip(surfaces,before):
        assert w.geometry()==geometry and w.backdrop.cacheKey()==key
        assert w.grab().toImage()==image,w.__class__.__name__
    assert not dock.blur_timer.isActive() and not dock.proc_timer.isActive()
    checks.append('lite mode preserves exact rendered Dock/card/note/clock/calendar pixels, geometry and backdrop; background polling stops')
    # Wallpaper/key caching is measured with a synthetic capture, not user data.
    calls=[]
    dock.preview=False;cfg.update(glass=True,clear_background=False,dock_material='liquid')
    with patch('glass_capture.backdrop_key',return_value=('fixed',)),patch.object(dock,'_capture_behind',side_effect=lambda:(calls.append(True) or surfaces[0].backdrop,True)):
        dock._backdrop_key=None
        for _ in range(10):dock.refresh_backdrop()
        assert len(calls)==1
    dock.preview=True
    def cycle():
        runtime.set_lite(False)
        QTimer.singleShot(0,lambda:app.activeModalWidget().reject())
        runtime.open_card_sizing()
        runtime.set_lite(True)
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
    (Path(output)/'lite-memory.json').write_text(json.dumps(dict(baseline_private_bytes=baseline,final_private_bytes=samples[-1],peak_private_bytes=max(samples),cycles=20,limits='short local synthetic scenario, not long-duration user workload'),indent=2),encoding='utf-8')
    checks.append('unchanged wallpaper blurs once across ten refreshes; 20 mode cycles retain bounded QObject count and private memory')
    runtime.set_lite(False)
