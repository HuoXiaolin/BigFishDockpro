"""Manage desktop visibility, fullscreen pausing and background services."""
from functools import cached_property
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import QApplication, QDialog
from screen_corners import CornerManager
from platform_services import foreground_fullscreen, fullscreen_window, set_priority
from update_service import UpdateService


class RuntimeController:
    @cached_property
    def face_roles(self):
        from face_roles import RoleLibrary
        return RoleLibrary(self.api.CONFIG_DIR)

    def refresh_face_roles(self, role_id):
        if self.resources.window is not None and self.dock.cfg['resource_face_role']==role_id:
            self.resources.window.update()
        if self.dock.cfg['panel_face_role']==role_id:
            for window in self.panels.windows.values():
                if window.isVisible():
                    window.update()

    def __init__(self, dock, tray, api, from_logon=False):
        self.dock, self.tray, self.api = dock, tray, api
        from component_passthrough import ClickThroughPolicy
        dock.setProperty('clickThroughKey','dock');self.click_policy=ClickThroughPolicy(self)
        from usage_stats import UsageStore
        self.usage=dock.usage=UsageStore(api.CONFIG_DIR,dock,api.log)
        self.closed = False
        self.session_ending=False
        if from_logon:
            from time import monotonic
            self.bridge_start_after = monotonic() + 5
        self.auto_game = False
        self.game_active = False
        self.manual_game = False
        from desktop_panels import DesktopPanels
        self.panels = DesktopPanels(self)
        self.settings_open = False
        self.was_dock_visible = self.dock.cfg['dock_visible']
        self.corners = CornerManager()
        from taskbar_appearance import TaskbarAppearance
        self.taskbar = TaskbarAppearance(dock, api.log)
        from desktop_shortcut import DesktopMiddleShortcut
        import os
        self.desktop_shortcut=DesktopMiddleShortcut(dock,disabled=dock.preview or bool(os.environ.get('FISHDOCK_TEST_DESKTOP')))
        self.desktop_shortcut.triggered.connect(lambda:self.panels.toggle_desktop_icons())
        self.updater = UpdateService(self)
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
            if signal is not None:
                callback=self.commit_session if name=='commitDataRequest' else self.checkpoint_session
                signal.connect(callback);self._session_signals.append((signal,callback))
        from screen_layout import DisplayLayout
        from sticky_notes import NotesManager
        self.notes=NotesManager(self)
        from desktop_clock import DesktopClock
        self.clock=DesktopClock(self)
        from desktop_calendar import DesktopCalendar
        self.calendar=DesktopCalendar(self)
        from flash_capsule import FlashCapsule
        self.flash=FlashCapsule(self)
        self.spectrum = None
        self.daily_picture = None
        self.custom_cards = None
        from resource_capsule import ResourceCapsule
        self.resources=ResourceCapsule(self)
        self.notes.changed.connect(self.resources.components_changed)
        self.layout = DisplayLayout(self)
        from productivity import Productivity
        self.productivity=Productivity(self)
        self._update_source_key=self.updater.source_key()
        from interaction_motion import attach
        for window in (self.dock,self.clock,self.calendar):attach(window,lambda:self.dock.cfg)
        self.apply_settings()
        self._wallpaper_keys={}
        self.wallpaper_timer=QTimer(self.dock)
        self.wallpaper_timer.setTimerType(Qt.VeryCoarseTimer)
        self.wallpaper_timer.setInterval(5000)
        self.wallpaper_timer.timeout.connect(self.check_wallpaper)
        if not self.dock.preview:self.wallpaper_timer.start()
        from memory_budget import MemoryBudget
        self.memory_budget=MemoryBudget(self)
        from window_layers import ForegroundLayers
        self.foreground_layers=None if dock.preview else ForegroundLayers(dock,self.refresh_layers)
        if not dock.preview and not os.environ.get('FISHDOCK_TEST_DESKTOP'):
            status=api.config_status()
            if status.get('message'):
                QTimer.singleShot(0,lambda:self.tray.showMessage('配置恢复',status['message'],self.tray.icon(),6000) if not self.closed else None)

    def screens_changed(self, *args):
        self.layout.changed(*args)

    def refresh_corners(self):
        # A fullscreen foreground window may be a browser/video, not a game.
        self.corners.apply(self.dock.cfg['screen_corners'] and not self.dock.cfg['game_mode'],
                           self.dock.cfg['corner_radius'])

    def ui_busy(self):
        from glass_panel import DesktopPanel
        return any(isinstance(widget,QDialog) and not isinstance(widget,DesktopPanel) and widget.isVisible()
                   for widget in QApplication.topLevelWidgets()) or bool(QApplication.activePopupWidget())

    def show_settings(self):
        self.tray.show_settings()

    def settings_closed(self):
        self.settings_open = False
        self.resources.set_main_settings(False)
        self.check_fullscreen()

    def show_batch(self):
        self.tray.importer.show()

    def show_panel(self):
        if not self.dock.cfg['panel_enabled']:
            self.tray.showMessage('桌面面板', '请先在设置中启用桌面收纳面板。', self.tray.icon(), 3000)
            return
        if self.dock.cfg['game_mode']:
            self.set_desktop_paused(False)
        self.panels.reveal()

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
            self.set_desktop_paused(False)
            self.auto_game = False
            self.apply_visibility()
            self.set_dock_visible(True)
        else: self.set_dock_visible(not self.dock.isVisible())

    def set_desktop_paused(self, enabled):
        from settings_effects import save_changes
        return save_changes(self.tray, self.api, {'game_mode': bool(enabled)})

    def set_fullscreen_pause(self, enabled):
        from settings_effects import save_changes
        return save_changes(self.tray, self.api, {'fullscreen_detection': bool(enabled)})

    def configure_fullscreen_timer(self):
        if self.dock.cfg['fullscreen_detection']:
            if not self.fullscreen_timer.isActive():self.fullscreen_timer.start()
        else:
            self.fullscreen_timer.stop()
        self.check_fullscreen()

    def check_fullscreen(self):
        self.auto_game = bool(self.dock.cfg['fullscreen_detection'] and
                              not self.settings_open and foreground_fullscreen())
        self.apply_visibility()
        self.refresh_corners()

    def apply_visibility(self):
        manual = self.dock.cfg['game_mode'] and not self.settings_open
        active = (manual or self.auto_game) and not self.settings_open
        changed=active!=self.game_active;self.game_active=active
        manual_changed=manual!=self.manual_game;self.manual_game=manual
        # Saved intent owns visibility; temporary game/shutdown hides never do.
        self.was_dock_visible=bool(self.dock.cfg['dock_visible'])
        wanted=self.was_dock_visible and not active
        if wanted and not self.dock.isVisible():self.tray._show_dock()
        elif not wanted and self.dock.isVisible():self.dock.hide()
        if changed:
            self.dock.sync_background_polling(refresh=not active)
            self.panels.set_blocked(active);self.notes.sync();self.clock.sync();self.calendar.sync();self.flash.sync()
            self.sync_spectrum()
            self.sync_daily_picture()
            self.sync_custom_cards()
            self.resources.sync()
        elif manual_changed:self.resources.sync()
        self.refresh_corners()

    def refresh_layers(self):
        if self.closed:return
        strip=self.resources.strip
        if strip:strip.placement.shell_changed()
        capsule=self.resources.window
        if capsule and capsule.taskbar_placement:capsule.taskbar_placement.shell_changed()
        cfg=self.dock.cfg
        windows=[self.dock if cfg['layer']=='top' else None,
                 capsule if cfg['resource_layer']=='top' and capsule and capsule.taskbar_slot() is None else None,
                 self.flash.edge,self.flash.panel,self.flash.toast]
        windows.extend(note for note in self.notes.windows.values() if note.row()['pinned'])
        visible=[w for w in windows if w is not None and w.isWindow() and w.isVisible()]
        if visible:
            from window_layers import repair_top
            cover=fullscreen_window()
            for w in visible:repair_top(int(w.winId()),cover)

    def apply_settings(self,changed=None):
        if changed is not None:changed=set(changed)
        placement_changed=changed is None or 'resource_component_locations' in changed
        policy_keys={'passthrough_mode','component_passthrough','resource_click_through','resource_taskbar_click_through'}
        policy_changed=changed is None or bool(changed&policy_keys)
        if changed is not None and 'motion_enabled' in changed:
            for window in self.panels.windows.values():window.face_tracker.sync_face();window.update()
        if self.updater.source_key()!=getattr(self,'_update_source_key',None):
            self.updater.settings_changed();self._update_source_key=self.updater.source_key()
        if changed is not None and 'motion_enabled' in changed and not self.dock.cfg.get('motion_enabled',True):
            for window in [self.dock,self.clock,self.calendar,*self.panels.windows.values(),*self.notes.windows.values()]:
                controller=getattr(window,'_interaction_motion',None)
                if controller:controller.stop()
        capsule_style={'theme','theme_color','panel_color','panel_theme','panel_material','panel_highlight','panel_opacity','panel_blur','card_design'}
        if changed is None or any(key.startswith('spectrum_') for key in changed) or changed & {'theme','theme_color','card_scale'}:
            self.sync_spectrum()
        if placement_changed or any(key.startswith('daily_picture_') for key in changed) or changed & (capsule_style|{'card_scale'}):
            self.sync_daily_picture()
        if placement_changed or changed & (capsule_style|{'card_scale','custom_cards'}):
            self.sync_custom_cards()
        if policy_changed or any(key.startswith('resource_') for key in changed) or changed & (capsule_style|{'taskbar_text_mode','motion_enabled','card_snap','spectrum_enabled','custom_cards','calendar_enabled'}):
            self.resources.sync()
        if changed is None or any(key.startswith('flash_') for key in changed) or changed & capsule_style:
            self.flash.sync()
        if changed is None or any(key.startswith('taskbar_') for key in changed):
            self.taskbar.sync()
            if self.resources.ai_tray and (changed is None or 'taskbar_text_mode' in changed):
                self.resources.ai_tray.sync_taskbar_text()
        if changed is not None:
            if 'desktop_middle_toggle' in changed:self.desktop_shortcut.set_enabled(self.dock.cfg['desktop_middle_toggle'])
            if 'hide_tray' in changed or policy_changed:self.sync_tray_visibility()
            panel_keys={key for key in changed if key.startswith(('panel_','desktop_','merged_','merge_')) and key!='desktop_middle_toggle'}
            if panel_keys or changed&{'card_scale','card_sizing','display_layout','card_design'}:self.panels.apply_settings()
            if placement_changed or changed&{'note_style','note_appearance','notes_enabled','notes_visible','sticky_notes','card_scale','card_sizing','card_design'}:self.notes.sync()
            if placement_changed or any(key.startswith('clock_') for key in changed) or changed&{'card_scale','card_design'}:self.clock.sync()
            if placement_changed or any(key.startswith('calendar_') for key in changed) or changed&{'card_scale','card_design'}:self.calendar.sync()
            if changed&{'clock_enabled','calendar_enabled','daily_picture_enabled','notes_enabled','notes_visible','sticky_notes','custom_cards'}:
                self.resources.components_changed()
            if 'card_scale' in changed:
                self.panels.reposition();self.notes.reposition();self.clock.reposition();self.calendar.reposition();self._card_density=self.dock.cfg['card_scale']
            if changed&{'screen_corners','corner_radius'}:self.refresh_corners()
            if 'fullscreen_detection' in changed:self.configure_fullscreen_timer()
            elif 'game_mode' in changed:self.apply_visibility()
            if 'startup_priority' in changed:set_priority(self.dock.cfg['startup_priority'])
            if policy_changed:self.click_policy.refresh()
            return
        self.desktop_shortcut.set_enabled(self.dock.cfg['desktop_middle_toggle'])
        self.sync_tray_visibility()
        self.panels.apply_settings()
        self.notes.sync()
        self.clock.sync();self.calendar.sync()
        density=self.dock.cfg.get('card_scale',70)
        if getattr(self,'_card_density',None)!=density:
            self.panels.reposition();self.notes.reposition();self.clock.reposition();self.calendar.reposition();self._card_density=density
        self.configure_fullscreen_timer()
        self.apply_visibility()
        if policy_changed:self.click_policy.refresh()
        self.refresh_corners()
        set_priority(self.dock.cfg['startup_priority'])

    def sync_tray_visibility(self):
        from component_passthrough import enabled
        self.tray.setVisible(not self.dock.cfg['hide_tray'] or enabled(self.dock.cfg,'dock'))

    def sync_spectrum(self):
        if self.dock.cfg['spectrum_enabled'] and not self.game_active:
            if self.spectrum is None:
                from desktop_spectrum import DesktopSpectrum
                self.spectrum = DesktopSpectrum(self)
            self.spectrum.sync()
        elif self.spectrum is not None:
            self.spectrum.hide()
            self.spectrum.deleteLater()
            self.spectrum = None

    def set_spectrum_options(self, **changes):
        from settings_effects import save_changes
        return save_changes(self.tray, self.api, changes)

    def sync_daily_picture(self):
        from resource_options import component_location
        cfg=self.dock.cfg
        routed=component_location(cfg,'picture')=='capsule'
        host=self.resources.hosted_component('picture') if routed else None
        visible=cfg['daily_picture_enabled'] and not self.game_active and (not routed or host is not None)
        if self.daily_picture and (not visible or self.daily_picture.parentWidget() is not host):
            self.daily_picture.hide();self.daily_picture.deleteLater();self.daily_picture=None
        if visible:
            if self.daily_picture is None:
                from daily_picture_card import DailyPictureCard
                self.daily_picture=DailyPictureCard(self,host)
                if host:host.layout().addWidget(self.daily_picture)
            self.daily_picture.sync()

    def sync_hosted_component(self,key):
        if key=='notes':self.notes.sync()
        elif key=='picture':self.sync_daily_picture()
        elif key=='custom':self.sync_custom_cards()
        else:getattr(self,key).sync()

    def wallpaper_targets(self):
        glass_windows=(self.resources.window,self.daily_picture,*self.resources.desktop_cards.values())
        glass=[(window,window.glass) for window in glass_windows
               if window is not None and window.isWindow() and window.isVisible()]
        panel=self.flash.panel
        if panel is not None:
            glass.extend((bar,bar.material) for bar in (panel.toolbar,panel.filters_bar,panel.launch_shell,panel.composer)
                         if bar.isVisible())
        windows=(self.clock,self.calendar,*self.panels.windows.values(),*self.notes.windows.values())
        captures=[window for window in windows if window.isWindow() and window.isVisible()]
        return glass,captures

    def refresh_wallpaper_targets(self,glass,captures):
        for window,material in glass:
            material.clear();window.update()
        for window in captures:
            window.refresh_timer.start()

    def wallpaper_changed(self):
        if self.closed or self.session_ending:return
        from wallpaper_source import invalidate_source
        invalidate_source()
        self.refresh_wallpaper_targets(*self.wallpaper_targets())

    def check_wallpaper(self):
        if self.closed or self.session_ending or self.dock.preview:return
        from wallpaper_source import wallpaper_key
        glass,captures=self.wallpaper_targets()
        # The main capsule and Dock already check their own wallpaper.
        glass=[(window,material) for window,material in glass
               if window is not self.resources.window and material.uses_wallpaper]
        captures=[window for window in captures if window.backdrop is not None]
        keys={}
        for window in [widget for widget,_ in glass]+captures:
            screen=QApplication.screenAt(window.frameGeometry().center()) or QApplication.primaryScreen()
            if screen is None or screen.name() in keys:continue
            try:keys[screen.name()]=wallpaper_key(window,screen)
            except (OSError,ValueError,RuntimeError,AttributeError):continue
        if any(self._wallpaper_keys.get(screen)!=key for screen,key in keys.items()):
            self.refresh_wallpaper_targets(glass,captures)
        self._wallpaper_keys=keys

    def set_daily_picture_options(self, **changes):
        from settings_effects import save_changes
        return save_changes(self.tray,self.api,changes)

    def custom_card_manager(self):
        if self.custom_cards is None:
            from custom_cards import CustomCards
            self.custom_cards=CustomCards(self)
        return self.custom_cards

    def sync_custom_cards(self):
        if self.custom_cards or self.dock.cfg['custom_cards']:
            self.custom_card_manager().sync()

    def open_custom_cards(self):
        from contextlib import nullcontext
        dialog=getattr(self.tray,'settings_dialog',None)
        scope=dialog.suspend_page() if dialog and dialog.isVisible() else nullcontext()
        with scope:self.custom_card_manager().edit()

    def open_card_sizing(self,kind=None,identity=None):
        from card_sizing import CardSizingDialog
        from ui_style import exec_dialog
        exec_dialog(CardSizingDialog(self,kind,identity))

    def checkpoint_session(self,*args):
        if self.closed:return False
        from session_state import save_state
        return save_state(self)

    def set_session_ending(self,ending):
        if self.closed or self.session_ending==bool(ending):return
        self.session_ending=bool(ending)
        from probe_lifecycle import set_ending
        set_ending(ending)
        if ending:
            self.resources.suspend_session()
        else:
            # Windows can cancel shutdown. Recreate demand-driven collectors
            # after the native callback, with the user's existing preferences.
            QTimer.singleShot(0,self.resume_session)

    def resume_session(self):
        if self.closed or self.session_ending:return
        from probe_lifecycle import allowed
        if not allowed():
            QTimer.singleShot(250,self.resume_session)
            return
        self.resources.sync()

    def commit_session(self,*args):
        self.set_session_ending(True)
        return self.checkpoint_session()

    def request_exit(self):
        if not self.flash.save_draft(): return False
        if not self.notes.flush() and not self.notes.backup():
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(None,'便签尚未保存','无法保存便签或恢复备份。请先复制内容或修复数据目录，再退出。')
            return False
        QApplication.instance().quit()
        return True

    def close(self):
        if self.closed: return
        self.click_policy.close()
        self.closed = True
        self.wallpaper_timer.stop()
        from probe_lifecycle import set_ending
        set_ending(True)
        if hasattr(self,'memory_budget'):self.memory_budget.close()
        shutdown=self.session_ending or QApplication.instance().isSavingSession()
        importer=getattr(self.tray,'importer',None)
        if importer:importer.close()
        self.updater.close(wait_ms=0 if shutdown else 100)
        if self.panels.worker:self.panels.worker.cancelled.set()
        from session_state import save_state
        save_state(self)
        self.resources.close()
        if self.custom_cards:self.custom_cards.close()
        if self.daily_picture is not None:
            self.daily_picture.hide()
            self.daily_picture.deleteLater()
            self.daily_picture=None
        if self.spectrum is not None:
            self.spectrum.hide()
            self.spectrum.deleteLater()
            self.spectrum = None
        self.flash.close()
        self.layout.close()
        for timer in (self.dock.proc_timer,self.dock.geo_timer,self.dock.blur_timer,self.dock.timer,self.dock.folder_timer):timer.stop()
        if hasattr(self,'productivity'):self.productivity.close()
        from wallpaper_source import image_file
        image_file.cache_clear()
        self.dock.extras.close()
        self.desktop_shortcut.close()
        self.usage.close()
        for signal,callback in self._session_signals:
            try:signal.disconnect(callback)
            except (TypeError,RuntimeError):pass
        self._session_signals.clear()
        self.notes.close(save=False)
        self.clock.dispose(save_geometry=False);self.calendar.dispose(save_geometry=False)
        self.fullscreen_timer.stop()
        if self.foreground_layers:self.foreground_layers.close()
        self.corners.close()
        self.panels.close(save_geometry=False,wait_ms=0 if shutdown else 100)
        self.taskbar.close(shutdown=shutdown)
