"""Persist visibility intent while simulating shutdown and live settings changes."""
import copy
from unittest.mock import patch
from PyQt5.QtWidgets import QApplication


def run(api,runtime,checks):
    cfg=runtime.dock.cfg;original=copy.deepcopy(cfg);dialog=None
    try:
        cfg.update(game_mode=False,fullscreen_detection=False,panel_enabled=True,panels_visible=True,notes_enabled=True,notes_visible=True,clock_enabled=True)
        runtime.apply_settings();runtime.set_dock_visible(True)
        runtime.tray.rebuild()
        pause_menu = next(action.menu() for action in runtime.tray.menu.actions() if action.text() == '组件暂停')
        manual, automatic = pause_menu.actions()
        assert not manual.isChecked() and not automatic.isChecked()
        with patch('runtime_controller.foreground_fullscreen', return_value=True) as fullscreen:
            automatic.trigger()
            assert runtime.game_active and runtime.fullscreen_timer.isActive() and not cfg['game_mode']
            manual.trigger()
            assert runtime.game_active and cfg['game_mode'] and cfg['fullscreen_detection']
            automatic.trigger()
            assert runtime.game_active and cfg['game_mode'] and not runtime.fullscreen_timer.isActive()
            manual.trigger()
            assert not runtime.game_active and runtime.dock.isVisible()
            automatic.trigger()
            assert runtime.game_active
            fullscreen.return_value = False
            runtime.check_fullscreen()
            assert not runtime.game_active and runtime.dock.isVisible()
            saved = api.load_config()
            assert saved['fullscreen_detection'] and not saved['game_mode']
            automatic.trigger()
        checks.append('Desktop pause: independent tray toggles, automatic fullscreen resume, manual pause survives disabling automatic pause, and persisted preferences match.')
        note_id=runtime.notes.new();note=runtime.notes.windows[note_id]
        panel=next(window for window in runtime.panels.windows.values() if window.isVisible())
        collapsed=panel.collapsed
        assert not QApplication.instance().isFallbackSessionManagementEnabled()
        # Run actual closeEvent dispatch under a session-save condition. No user
        # desktop session is ended, and no native window outside this fixture is used.
        with patch.object(QApplication,'isSavingSession',return_value=True):
            note.close();panel.close();runtime.dock.close()
        assert runtime.notes.row(note_id)['visible'] and panel.collapsed==collapsed
        assert runtime.checkpoint_session(object())
        saved=api.load_config()
        assert all(saved[key] for key in ('dock_visible','panels_visible','notes_visible','clock_enabled'))
        runtime.apply_settings()
        assert runtime.dock.isVisible() and panel.isVisible() and runtime.clock.isVisible() and note.isVisible()
        runtime.set_dock_visible(False);runtime.panels.toggle();runtime.notes.toggle();runtime.clock.set_enabled(False)
        assert all(not api.load_config()[key] for key in ('dock_visible','panels_visible','notes_visible','clock_enabled'))
        runtime.set_desktop_paused(True);runtime.set_desktop_paused(False)
        assert not runtime.dock.isVisible() and not panel.isVisible() and not runtime.clock.isVisible() and not note.isVisible()
        with patch.object(api,'save_config',return_value=False):
            runtime.set_dock_visible(True);assert runtime.panels.reveal() is False;runtime.notes.toggle();runtime.clock.set_enabled(True)
        assert all(not cfg[key] for key in ('dock_visible','panels_visible','notes_visible','clock_enabled'))
        # An unrelated main-settings save must not restore an obsolete clock switch.
        from settings_dialog import SettingsDialog
        dialog=SettingsDialog(runtime.tray,api);dialog.reveal();runtime.clock.set_enabled(True)
        dialog.fields['icon_size'].setValue(dialog.fields['icon_size'].value()+1);dialog.commit()
        assert cfg['clock_enabled'] and dialog.fields['clock_enabled'].isChecked()
        dialog.reject();dialog.deleteLater();dialog=None
        # A programmatic/imported visibility change must update the panel manager too.
        cfg['panels_visible']=True;runtime.apply_settings();assert runtime.panels.shown and any(w.isVisible() for w in runtime.panels.windows.values()),(cfg['panel_enabled'],runtime.panels.shown,runtime.panels.blocked,runtime.panels.closed,len(runtime.panels.enabled_models()),cfg['disabled_categories'],runtime.game_active,cfg['game_mode'])
        cfg['panels_visible']=False;runtime.apply_settings();assert not runtime.panels.shown and not any(w.isVisible() for w in runtime.panels.windows.values())
        checks.append('visibility persistence: real close events during simulated session saving preserve Dock/card/note intent and collapse; shutdown checkpoint, live hidden toggles, desktop pause, failed save, stale main settings and imported panel visibility exercised; Qt fallback session close disabled; no OS reboot performed')
    finally:
        if dialog:dialog.reject();dialog.deleteLater()
        cfg.clear();cfg.update(original);api.save_config(cfg);runtime.notes.reload();runtime.apply_settings()
