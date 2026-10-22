"""Runtime state machine: normal, lightweight, manual/automatic game mode."""
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication
from screen_corners import CornerManager
from platform_services import foreground_fullscreen, set_priority
from update_service import UpdateService


class RuntimeController:
    def __init__(self, dock, tray, api):
        self.dock, self.tray, self.api = dock, tray, api
        self.lite = False
        self.closed = False
        self.auto_game = False
        self.game_active = False
        from desktop_panels import DesktopPanels
        self.panels = DesktopPanels(self)
        self.settings_open = False
        self.was_dock_visible = dock.isVisible()
        self.corners = CornerManager()
        self.updater = UpdateService(self)
        self.lite_timer = QTimer(dock)
        self.lite_timer.setSingleShot(True)
        self.lite_timer.setInterval(60000)
        self.lite_timer.timeout.connect(self.enter_lite_if_allowed)
        self.fullscreen_timer = QTimer(dock)
        self.fullscreen_timer.setInterval(1500)
        self.fullscreen_timer.timeout.connect(self.check_fullscreen)
        app = QApplication.instance()
        app.aboutToQuit.connect(self.close)
        app.screenAdded.connect(self.screens_changed)
        app.screenRemoved.connect(self.screens_changed)
        for screen in app.screens():
            screen.geometryChanged.connect(self.screens_changed)
        self.apply_settings()
        self.arm_lite()

    def screens_changed(self, *args):
        self.dock.reposition()
        self.panels.reposition()
        self.refresh_corners()

    def refresh_corners(self):
        # A fullscreen foreground window may be a browser/video, not a game.
        # Static masks also stay available in lite mode without adding polling.
        self.corners.apply(self.dock.cfg['screen_corners'] and not self.dock.cfg['game_mode'],
                           self.dock.cfg['corner_radius'])

    def arm_lite(self):
        self.lite_timer.stop()
        if self.dock.cfg['lite_enabled'] and not self.settings_open and not self.lite:
            self.lite_timer.start(60000)

    def enter_lite_if_allowed(self):
        if self.dock.cfg['lite_enabled'] and not self.settings_open:
            self.set_lite(True)

    def set_lite(self, enabled):
        self.lite = bool(enabled)
        self.dock.lite_mode = self.lite
        if enabled:
            self.lite_timer.stop()
            self.panels.set_lite(True)
            self.fullscreen_timer.stop()
            self.dock.blur_timer.stop()
            self.dock.proc_timer.stop()
            self.dock.geo_timer.stop()
            self.dock.backdrop = None
            self.dock.icons.clear()
            for item in self.dock.items: item.pop('_scaled', None)
            importer = getattr(self.tray, 'importer', None)
            if importer: importer.release_memory()
            from app_catalog import clear_discovery_cache
            from PyQt5.QtGui import QPixmapCache
            clear_discovery_cache()
            QPixmapCache.clear()
            self.dock.running.clear()
            set_priority('low')
            # An auto-game session must not leave the Dock hidden after detection stops.
            self.auto_game = False
            self.apply_visibility()
        else:
            set_priority(self.dock.cfg['startup_priority'])
            if not self.dock.preview:
                self.dock.geo_timer.start(2500)
                if self.dock.cfg['running_dots']:
                    self.dock.proc_timer.start(8000)
                self.dock.start_backdrop()
            self.configure_fullscreen_timer()
            self.apply_visibility()
            self.refresh_corners()
            self.panels.set_lite(False)
        self.dock._recalc(uniform=True)
        self.dock._kick()
        self.tray.setToolTip('大肥鱼Dock · '+('精简模式' if self.lite else '完整模式'))

    def show_settings(self):
        self.settings_open = True
        self.lite_timer.stop()
        self.set_lite(False)
        self.tray.show_settings()

    def settings_closed(self):
        self.settings_open = False
        self.check_fullscreen()
        self.arm_lite()

    def show_batch(self):
        self.set_lite(False)
        self.tray.importer.show()
        self.arm_lite()

    def show_panel(self):
        if not self.dock.cfg['panel_enabled']:
            self.tray.showMessage('桌面面板', '请先在设置中启用桌面收纳面板。', self.tray.icon(), 3000)
            return
        if self.dock.cfg['game_mode']:
            self.toggle_game(False)
        self.set_lite(False)
        self.panels.reveal()
        self.arm_lite()

    def toggle_panels(self):
        if self.panels.shown and self.panels.windows:
            self.panels.toggle()
        else:
            self.show_panel()

    def toggle_dock(self):
        if self.game_active:
            self.toggle_game(False)
            self.auto_game = False
            self.apply_visibility()
            self.tray._show_dock()
            return
        if self.dock.isVisible():
            self.dock.hide()
        else:
            self.tray._show_dock()

    def toggle_game(self, enabled):
        candidate = dict(self.dock.cfg, game_mode=bool(enabled))
        if self.api.save_config(candidate):
            self.dock.cfg['game_mode'] = bool(enabled)
            self.apply_visibility()

    def configure_fullscreen_timer(self):
        if self.dock.cfg['fullscreen_detection'] and not self.lite:
            self.fullscreen_timer.start()
        else:
            self.fullscreen_timer.stop()
        self.check_fullscreen()

    def check_fullscreen(self):
        self.auto_game = bool(self.dock.cfg['fullscreen_detection'] and not self.lite and
                              not self.settings_open and foreground_fullscreen())
        self.apply_visibility()
        self.refresh_corners()

    def apply_visibility(self):
        active = bool(self.dock.cfg['game_mode'] or self.auto_game) and not self.settings_open
        if active == self.game_active:
            self.refresh_corners()
            return
        if active:
            self.was_dock_visible = self.dock.isVisible()
            self.dock.hide()
            self.dock.proc_timer.stop()
        else:
            if self.was_dock_visible:
                self.tray._show_dock()
            if not self.lite and not self.dock.preview and self.dock.cfg['running_dots']:
                self.dock.proc_timer.start(8000)
        self.game_active = active
        self.panels.set_blocked(active)
        self.refresh_corners()

    def apply_settings(self):
        if self.lite and not self.dock.cfg['lite_enabled']:
            self.set_lite(False)
        self.panels.apply_settings()
        self.configure_fullscreen_timer()
        self.apply_visibility()
        self.refresh_corners()
        set_priority('low' if self.lite else self.dock.cfg['startup_priority'])

    def close(self):
        if self.closed: return
        self.closed = True
        self.lite_timer.stop()
        self.fullscreen_timer.stop()
        self.corners.close()
        self.panels.close()
        self.updater.close()
