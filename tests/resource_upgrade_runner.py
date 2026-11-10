"""Focused native UI verification, launched only by run_isolated_test.py."""
import sys,json,tempfile,traceback,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/name) for name in ('app','tests','tools')]


def main():
    from run_isolated_test import assert_isolated
    desktop=assert_isolated()
    import dock as api
    from PyQt5.QtWidgets import QApplication
    from ui_style import apply_theme,shutdown_ui
    from runtime_controller import RuntimeController
    output=Path(sys.argv[-1]);output.mkdir(parents=True,exist_ok=True)
    app=QApplication([]);app.setQuitOnLastWindowClosed(False);apply_theme(app,True);checks=[];runtime=None
    with tempfile.TemporaryDirectory(prefix='fishdock-resource-') as root:
        api.CONFIG_DIR=root;api.CONFIG_PATH=str(Path(root)/'config.json');api.LOG_PATH=str(Path(root)/'dock.log')
        api.RUN_KEY=r'Software\BigFishDockpro_Test_'+desktop
        try:
            cfg=api.normalize_features(copy.deepcopy(api.DEFAULT_CONFIG));cfg.update(items=[],hide_tray=True,desktop_auto_sort=False,desktop_icon_mode='both',screen_corners=False)
            dock=api.Dock(cfg,preview=True);tray=api.DockTray(dock);dock.tray=tray
            runtime=tray.runtime=RuntimeController(dock,tray,api)
            from window_layer_tests import run as run_window_layers, bluetooth_rings
            run_window_layers(api,runtime,app,output,checks)
            bluetooth_rings(checks)
            from startup_tests import early_logon
            early_logon(root,checks)
            from reliability_state_tests import check_taskbar_shell_recovery
            check_taskbar_shell_recovery(checks)
            from flash_capsule_tests import run as flash
            flash(api,runtime,root,app,output,checks)
            from resource_capsule_tests import run as existing
            existing(api,runtime,root,app,output,checks)
            from resource_upgrade_tests import run as upgraded
            upgraded(api,runtime,root,app,output,checks)
            from resource_pomodoro_tests import run as pomodoro
            pomodoro(api,runtime,app,output,checks)
            from resource_gateway_tests import run as gateways
            gateways(api,runtime,app,output,checks)
            result=dict(passed=True,checks=checks,scope='isolated-resource-upgrade')
        except Exception:result=dict(passed=False,checks=checks,error=traceback.format_exc())
        finally:
            if runtime:runtime.close()
            shutdown_ui(app)
        (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if result['passed'] else 1


if __name__=='__main__':sys.exit(main())
