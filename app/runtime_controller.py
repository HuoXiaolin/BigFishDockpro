"""Runtime state machine: normal, lightweight, manual/automatic game mode."""
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication, QDialog
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
        self.was_dock_visible = self.dock.cfg['dock_visible']
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
        # Qt fallback closes every top-level window during logout. Our close
        # buttons mean hide/collapse, so session shutdown must save separately.
        app.setFallbackSessionManagementEnabled(False)
        self._session_signals=[]
        for name in ('commitDataRequest','saveStateRequest'):
            signal=getattr(app,name,None)
            if signal is not None:signal.connect(self.checkpoint_session);self._session_signals.append(signal)
        from screen_layout import DisplayLayout
        from sticky_notes import NotesManager
        self.notes=NotesManager(self)
        from desktop_clock import DesktopClock
        self.clock=DesktopClock(self)
        from desktop_calendar import DesktopCalendar
        self.calendar=DesktopCalendar(self)
        self.layout = DisplayLayout(self)
        self.apply_settings()
        if self.dock.cfg.get('runtime_lite'): self.set_lite(True, persist=False)
        self.arm_lite()

    def screens_changed(self, *args):
        self.layout.changed(*args)

    def refresh_corners(self):
        # A fullscreen foreground window may be a browser/video, not a game.
        # Static masks also stay available in lite mode without adding polling.
        self.corners.apply(self.dock.cfg['screen_corners'] and not self.dock.cfg['game_mode'],
                           self.dock.cfg['corner_radius'])

    def arm_lite(self):
        self.lite_timer.stop()
        if self.dock.cfg['lite_enabled'] and not self.settings_open and not self.lite:
            self.lite_timer.start(60000)

    def ui_busy(self):
        from glass_panel import DesktopPanel
        return any(isinstance(widget,QDialog) and not isinstance(widget,DesktopPanel) and widget.isVisible()
                   for widget in QApplication.topLevelWidgets()) or bool(QApplication.activePopupWidget())

    def enter_lite_if_allowed(self):
        if self.dock.cfg['lite_enabled'] and not self.settings_open:
            if self.ui_busy(): self.lite_timer.start(60000)
            else: self.set_lite(True)

    def set_lite(self, enabled, persist=True):
        enabled = bool(enabled)
        was_lite = self.lite
        if enabled and was_lite: return
        restore = dict(self.dock.cfg.get('lite_restore',{}))
        if enabled and not (not persist and restore):
            restore = {key:window.collapsed for key,window in self.panels.windows.items()}
            restore['__merged__'] = self.dock.cfg['merged_collapsed']
            for group in self.dock.cfg.get('merge_groups',[]):
                if group['id']!='default':restore['__merge_group__'+group['id']]=group.get('collapsed',False)
        candidate = dict(self.dock.cfg,runtime_lite=enabled,lite_restore=restore)
        if persist and self.api.save_config(candidate) is False:
            self.api.log('运行模式保存失败，未切换模式。')
            return False
        self.dock.cfg.update(runtime_lite=enabled,lite_restore=restore)
        self.lite = enabled
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
            if was_lite:
                self.dock.cfg['merged_collapsed'] = self.dock.cfg.get('lite_restore',{}).get('__merged__',self.dock.cfg['merged_collapsed'])
                for group in self.dock.cfg.get('merge_groups',[]):
                    if group['id']!='default':group['collapsed']=self.dock.cfg.get('lite_restore',{}).get('__merge_group__'+group['id'],group.get('collapsed',False))
                self.panels.set_lite(False)
                self.dock.cfg['lite_restore'] = {}
                self.api.save_config(self.dock.cfg)
        self.notes.set_lite()
        self.clock.sync();self.calendar.sync()
        self.dock._recalc(uniform=True)
        self.dock._kick()
        self.tray.setToolTip('大肥鱼Dock · '+('精简模式' if self.lite else '完整模式'))
        if not enabled and not self.settings_open: self.arm_lite()
        return True

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

    def set_dock_visible(self, visible):
        if self.panels.commit(dock_visible=bool(visible)):
            self.was_dock_visible = bool(visible)
            if visible and not self.game_active: self.tray._show_dock()
            else: self.dock.hide()

    def toggle_dock(self):
        if self.game_active:
            self.toggle_game(False)
            self.auto_game = False
            self.apply_visibility()
            self.set_dock_visible(True)
        else: self.set_dock_visible(not self.dock.isVisible())

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
        changed=active!=self.game_active;self.game_active=active
        # Saved intent owns visibility; temporary game/shutdown hides never do.
        self.was_dock_visible=bool(self.dock.cfg['dock_visible'])
        wanted=self.was_dock_visible and not active
        if wanted and not self.dock.isVisible():self.tray._show_dock()
        elif not wanted and self.dock.isVisible():self.dock.hide()
        if changed:
            if active:self.dock.proc_timer.stop()
            elif not self.lite and not self.dock.preview and self.dock.cfg['running_dots']:self.dock.proc_timer.start(8000)
            self.panels.set_blocked(active);self.notes.sync();self.clock.sync();self.calendar.sync()
        self.refresh_corners()

    def apply_settings(self):
        if self.lite and not self.dock.cfg['lite_enabled']:
            self.set_lite(False)
        self.tray.setVisible(not self.dock.cfg['hide_tray'])
        self.panels.apply_settings()
        self.notes.sync()
        self.clock.sync();self.calendar.sync()
        density=self.dock.cfg.get('card_scale',70)
        if getattr(self,'_card_density',None)!=density:
            self.panels.reposition();self.notes.reposition();self.clock.reposition();self.calendar.reposition();self._card_density=density
        self.configure_fullscreen_timer()
        self.apply_visibility()
        self.refresh_corners()
        set_priority('low' if self.lite else self.dock.cfg['startup_priority'])
        if not self.settings_open: self.arm_lite()

    def open_card_sizing(self,kind=None,identity=None):
        from card_sizing import CardSizingDialog
        dialog=CardSizingDialog(self,kind,identity);dialog.exec_()

    def checkpoint_session(self,*args):
        if self.closed:return False
        if not self.notes.flush() and not self.notes.backup():self.api.log('结束会话前保存便签失败。')
        self.panels.save_visible_geometry();self.clock.save_geometry();self.calendar.save_geometry()
        candidate=dict(self.dock.cfg,runtime_lite=self.lite)
        if self.api.save_config(candidate) is False:
            self.api.log('结束会话前保存运行状态失败。');return False
        self.dock.cfg['runtime_lite']=self.lite;return True

    def request_exit(self):
        if not self.notes.flush() and not self.notes.backup():
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(None,'便签尚未保存','无法保存便签或恢复备份。请先复制内容或修复数据目录，再退出。')
            return False
        QApplication.instance().quit()
        return True

    def close(self):
        if self.closed: return
        self.closed = True
        for signal in self._session_signals:
            try:signal.disconnect(self.checkpoint_session)
            except (TypeError,RuntimeError):pass
        self._session_signals.clear()
        self.notes.close()
        self.clock.dispose();self.calendar.dispose()
        self.layout.close()
        self.dock.cfg['runtime_lite'] = self.lite
        self.api.save_config(self.dock.cfg)
        self.lite_timer.stop()
        self.fullscreen_timer.stop()
        self.corners.close()
        self.panels.close()
        self.updater.close()
