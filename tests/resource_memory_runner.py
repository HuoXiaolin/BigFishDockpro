"""Fresh-process memory samples; no account reads, playback commands or working-set trim."""
import copy,ctypes,json,os,statistics,sys,tempfile,time,traceback
from ctypes import wintypes as W
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/name) for name in ('app','tests','tools')]


class Counters(ctypes.Structure):
    _fields_=[('cb',W.DWORD),('PageFaultCount',W.DWORD)]+[(name,ctypes.c_size_t) for name in
        ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage','PrivateWorkingSetSize','SharedCommitUsage')]


def sample(pid):
    kernel=ctypes.WinDLL('kernel32');kernel.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];kernel.OpenProcess.restype=W.HANDLE;kernel.CloseHandle.argtypes=[W.HANDLE]
    handle=kernel.OpenProcess(0x410,False,pid)
    if not handle:raise ctypes.WinError()
    try:
        get=ctypes.WinDLL('psapi').GetProcessMemoryInfo;get.argtypes=[W.HANDLE,ctypes.c_void_p,W.DWORD];get.restype=W.BOOL
        data=Counters();data.cb=ctypes.sizeof(data)
        if not get(handle,ctypes.byref(data),data.cb):raise ctypes.WinError()
        return {k:round(getattr(data,v)/2**20,2) for k,v in [('private_working_set_mib','PrivateWorkingSetSize'),('working_set_mib','WorkingSetSize'),('private_commit_mib','PrivateUsage'),('peak_private_commit_mib','PeakPagefileUsage')]}
    finally:kernel.CloseHandle(handle)


def main():
    from run_isolated_test import assert_isolated
    desktop=assert_isolated();output=Path(sys.argv[-1]);output.mkdir(parents=True,exist_ok=True)
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QProcess,QEvent,QRect,QRectF,QSize
    from PyQt5.QtGui import QImage,QColor
    from ui_style import apply_theme,shutdown_ui
    app=QApplication([]);app.setQuitOnLastWindowClosed(False);apply_theme(app,True)
    def pump(seconds):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:app.processEvents();time.sleep(.015)
    def measure(pid):
        values=[]
        for _ in range(5):pump(.15);values.append(sample(pid))
        return {k:statistics.median(row[k] for row in values) for k in values[0]}
    runtime=None;process=None;result={}
    try:
        import dock as api
        from runtime_controller import RuntimeController
        with tempfile.TemporaryDirectory(prefix='bigfish-memory-') as root:
            api.CONFIG_DIR=root;api.CONFIG_PATH=str(Path(root)/'config.json');api.LOG_PATH=str(Path(root)/'dock.log');api.RUN_KEY='Software\\BigFishDockpro_Test_'+desktop
            cfg=api.normalize_features(copy.deepcopy(api.DEFAULT_CONFIG));cfg.update(items=[],hide_tray=True,screen_corners=False,desktop_auto_sort=False,desktop_icon_mode='both',panel_enabled=False,lite_enabled=False,resource_ai=False,resource_music=False)
            dock=api.Dock(cfg,preview=True);tray=api.DockTray(dock);dock.tray=tray;runtime=tray.runtime=RuntimeController(dock,tray,api)
            pump(.7);result['main_idle']=measure(os.getpid())
            cfg.update(resource_enabled=True,resource_collapsed=True,resource_auto_hide=False);runtime.resources.sync();pump(.5)
            result['main_resource_folded']=measure(os.getpid())
            cfg.update(resource_ai=True,resource_music=True);runtime.resources.sync();pump(.5)
            result['main_ai_music_folded']=measure(os.getpid())
            # Decode a generated 4K wallpaper, not the user's desktop.
            picture=QImage(3840,2160,QImage.Format_RGB32);picture.fill(QColor('#517493'));path=Path(root)/'wallpaper.bmp';picture.save(str(path));del picture
            import wallpaper_source
            wall=wallpaper_source.image_file(str(path),1)
            result['wallpaper_decoded_bytes']=wall.sizeInBytes();result['wallpaper_decoded_dimensions']=[wall.width(),wall.height()]
            del wall;wallpaper_source.image_file.cache_clear()
            runtime.close();runtime=None;app.sendPostedEvents(None,QEvent.DeferredDelete);pump(.2)
            # Exercise the actual helper; empty provider set avoids credentials/logs.
            process=QProcess();process.start(str(ROOT/'artifacts/deck-bridge/BigFishDeckBridge.exe'),[str(Path(root)/'deck')])
            assert process.waitForStarted(5000)
            for label,music in [('helper_idle',False),('helper_music',True),('helper_music_off',False)]:
                process.write((json.dumps(dict(op='configure',ai=False,providers=[],music=music,lyrics=False,equalizer='flow'))+'\n').encode())
                pump(2.5);process.readAllStandardOutput();process.readAllStandardError();result[label]=measure(int(process.processId()))
            process.write(b'{"op":"quit"}\n');assert process.waitForFinished(3500) and process.exitCode()==0
            result.update(passed=True,scope='fresh isolated source process, empty profile, generated 4K wallpaper and actual media discovery; no account reads/playback commands; no memory trimming')
    except Exception:result.update(passed=False,error=traceback.format_exc())
    finally:
        if process and process.state()!=QProcess.NotRunning:process.kill();process.waitForFinished(3000)
        if runtime:runtime.close()
        shutdown_ui(app)
    (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');return 0 if result.get('passed') else 1


if __name__=='__main__':sys.exit(main())
