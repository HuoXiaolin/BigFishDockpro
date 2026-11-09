"""Private-desktop memory attribution using the existing profile, without network or desktop changes."""
import copy,json,os,sys,tempfile,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/name) for name in ('app','tests','tools')]


def main():
    from run_isolated_test import assert_isolated
    desktop=assert_isolated();output=Path(sys.argv[-1]);output.mkdir(parents=True,exist_ok=True)
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QEvent
    from PyQt5.QtGui import QImage,QPixmap
    from resource_memory_runner import sample
    from ui_style import apply_theme,shutdown_ui
    app=QApplication([]);app.setQuitOnLastWindowClosed(False);apply_theme(app,True)
    runtime=None;result={'stages':[]}
    cold = os.environ.get('FISHDOCK_SETTINGS_COLD') == '1'
    def pump(seconds=.2):
        end=time.monotonic()+seconds
        while time.monotonic()<end:app.processEvents();time.sleep(.01)
        app.sendPostedEvents(None,QEvent.DeferredDelete)
    def stage(name):
        pump()
        windows=[]
        for w in QApplication.topLevelWidgets():
            images={}
            for key in ('backdrop','image','_backdrop'):
                image=getattr(w,key,None)
                if isinstance(image,(QImage,QPixmap)):images[key]=image.width()*image.height()*image.depth()//8
            glass=getattr(w,'glass',None)
            if glass and getattr(glass,'image',None) is not None:images['glass']=glass.image.width()*glass.image.height()*4
            windows.append(dict(type=type(w).__name__,visible=w.isVisible(),size=[w.width(),w.height()],pixels=images))
        row=dict(name=name,memory=sample(os.getpid()),windows=windows,icons_bytes=runtime.dock.icons.cache_bytes if runtime else 0)
        result['stages'].append(row)
    try:
        api=sys.modules.get('__main__')
        if not hasattr(api,'Dock'):
            import dock as api
        from runtime_controller import RuntimeController
        raw=json.loads((Path(os.environ['APPDATA'])/'BigFishDock/config.json').read_text(encoding='utf-8-sig'))
        with tempfile.TemporaryDirectory(prefix='bigfish-profile-memory-') as root:
            api.CONFIG_DIR=root;api.CONFIG_PATH=str(Path(root)/'config.json');api.LOG_PATH=str(Path(root)/'dock.log');api.RUN_KEY='Software\\BigFishDockpro_Test_'+desktop
            cfg=api.normalize_features(copy.deepcopy(raw));cfg.update(desktop_icon_mode='both',desktop_auto_sort=False,screen_corners=False,check_updates_on_start=False,hide_tray=True)
            stage('imports')
            dock=api.Dock(cfg,preview=True);tray=api.DockTray(dock);dock.tray=tray
            runtime=tray.runtime=RuntimeController(dock,tray,api);pump(1);stage('configured_preview')
            # Wallpaper-only material is safe on the private desktop; the original
            # capture function never sees foreground applications. No live GDI.
            from wallpaper_source import capture
            from glass_capture import smooth_backdrop
            screens=QApplication.screens()
            for w in QApplication.topLevelWidgets():
                if w.isVisible() and hasattr(w,'backdrop'):
                    screen=QApplication.screenAt(w.geometry().center()) or screens[0]
                    try:w.backdrop=smooth_backdrop(capture(w,screen),8);w.update()
                    except (OSError,ValueError,RuntimeError):pass
            stage('with_wallpaper_material')
            w = runtime.resources.window
            if not cold:
                cfg.update(resource_collapsed=False,resource_auto_hide=False);runtime.resources.sync()
                if w:
                    for key in ('resources','ai','music','traffic','weather'):
                        w.select_page(key);pump();w.grab()
                stage('all_resource_pages_visited')
                cfg['resource_collapsed']=True;runtime.resources.sync();stage('resource_folded_again')
            from resource_metrics import Sampler
            sampler=Sampler(runtime.resources.active_keys() if cold else {'cpu','memory','network','gpu','cpu_cores','rank'})
            try:
                for _ in range(4):sampler.sample();pump(.4)
                stage('with_native_counters')
                if os.environ.get('FISHDOCK_SETTINGS_PROFILE')=='1':
                    from resource_settings import ResourceOptions
                    if not cold:
                        cfg['resource_collapsed'] = False
                    cfg.update(resource_face=True,resource_face_interactive=True,panel_face=True,panel_face_interactive=True)
                    runtime.panels.apply_settings()
                    runtime.resources.auto_compact=None
                    runtime.resources.sync()
                    if not cold:
                        for key in ('resources','ai','music','traffic','weather','resources'):
                            w.select_page(key);runtime.resources.accept_sample(sampler.sample());pump(.12)
                    was_compact = runtime.resources.compact
                    stage('settings_baseline')
                    started=time.perf_counter();tray.show_settings();pump(.15)
                    settings=tray.settings_dialog
                    assert runtime.resources.compact and w.liquid.watch.isActive()
                    sampler.configure(runtime.resources.active_keys())
                    runtime.resources.accept_sample(sampler.sample())
                    result['settings_open_ms_including_150ms_pump']=round((time.perf_counter()-started)*1000,2)
                    result['settings_size']=[settings.width(),settings.height(),settings.devicePixelRatioF()]
                    stage('main_settings_open')
                    for index in range(settings.tabs.count()):
                        settings.tabs.setCurrentIndex(index);stage(f'main_settings_tab_{index}')
                    settings.tabs.setCurrentIndex(1)
                    saved_distance = cfg['card_snap_distance']
                    settings.fields['card_snap_distance'].setValue(21 if saved_distance != 21 else 22)
                    wanted_distance = settings.fields['card_snap_distance'].value()
                    with settings.suspend_page():
                        options=ResourceOptions(runtime.resources);options.show();stage('nested_resource_settings_open')
                        for index in range(options.tabs.count()):
                            options.tabs.setCurrentIndex(index);stage(f'nested_resource_settings_tab_{index}')
                        options.reject();options.deleteLater();pump()
                    assert settings.fields['card_snap_distance'].value() == wanted_distance
                    assert cfg['card_snap_distance'] == saved_distance
                    settings.reject();pump()
                    assert runtime.resources.compact == was_compact and w.liquid.watch.isActive()
                    runtime.memory_budget.reclaim();stage('settings_closed')
                    runtime.resources.settings_depth += 1
                    runtime.resources.settings_focus_changed()
                    try:
                        options=ResourceOptions(runtime.resources);options.show();stage('standalone_resource_settings_open')
                        for index in range(options.tabs.count()):
                            options.tabs.setCurrentIndex(index);stage(f'standalone_resource_settings_tab_{index}')
                        options.reject();options.deleteLater();pump()
                    finally:
                        runtime.resources.settings_depth -= 1
                        runtime.resources.settings_focus_changed()
                if os.environ.get('FISHDOCK_MEMORY_STRESS')=='1':
                    cfg.update(panel_face=True,panel_face_interactive=True);runtime.panels.apply_settings()
                    cfg.update(resource_collapsed=False,resource_face=True,resource_face_interactive=True);runtime.resources.auto_compact=None;runtime.resources.sync()
                    timings=[]
                    for cycle in range(3):
                        for page in ('resources','ai','music','traffic','weather'):
                            started=time.perf_counter();w.select_page(page);runtime.resources.accept_sample(sampler.sample());pump(.1);w.grab()
                            timings.append((time.perf_counter()-started)*1000)
                    stage('sampled_pages_after_cycles')
                    from resource_settings import ResourceOptions
                    options=ResourceOptions(runtime.resources);options.show();pump();stage('resource_options_open')
                    options.reject();options.deleteLater();pump();runtime.memory_budget.reclaim();pump();stage('after_options_reclaimed')
                    # Use the production sampler and allocator policy while painting
                    # actual values repeatedly. No forced GC or working-set trim.
                    w.select_page('resources');cfg['resource_collapsed']=True;runtime.resources.sync()
                    for cycle in range(int(os.environ.get('FISHDOCK_MEMORY_SOAK','30'))):
                        runtime.resources.accept_sample(sampler.sample());pump(1);w.grab()
                    stage('sampled_idle_after_soak')
                    result['cycle_switch_max_ms_including_100ms_pump']=round(max(timings),2)
            finally:sampler.close()
            stage('native_counters_closed')
            cfg.update(resource_enabled=False,resource_ai_tray=False,resource_taskbar=False,resource_bt_tray=False);runtime.resources.sync();stage('resource_closed')
            cfg.update(clock_enabled=False,flash_enabled=False,calendar_enabled=False,notes_enabled=False);runtime.clock.sync();runtime.flash.sync();runtime.calendar.sync();runtime.notes.sync();stage('extras_closed')
            cfg.update(panel_enabled=False,panels_visible=False);runtime.panels.apply_settings();stage('panels_closed')
            result.update(passed=True, cold_settings=cold,scope='Existing profile in preview on a private desktop; no account/network queries, playback, real notification reads, UI activation or working-set trimming. Window types and allocation sizes only; no personal content exported.')
    except Exception:result.update(passed=False,error=traceback.format_exc())
    finally:
        if runtime:runtime.close()
        shutdown_ui(app)
    (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if result.get('passed') else 1


if __name__=='__main__':sys.exit(main())
