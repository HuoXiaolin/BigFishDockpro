"""Native resize persistence, unified AI and collapsed remarks."""
import copy
from unittest.mock import patch
from PyQt5.QtCore import Qt,QPoint,QPointF,QEvent,QObject,QTimer
from PyQt5.QtGui import QCursor,QMouseEvent
from PyQt5.QtWidgets import QApplication


def visit_options(open_dialog, inspect):
    from resource_settings import ResourceOptions
    outcomes = []
    def inspect_open_dialog():
        dialog = QApplication.activeModalWidget()
        try:
            assert isinstance(dialog, ResourceOptions)
            inspect(dialog)
            outcomes.append(None)
        except Exception as error:
            outcomes.append(error)
        finally:
            if dialog is not None:dialog.reject()
    QTimer.singleShot(0, inspect_open_dialog)
    open_dialog()
    assert len(outcomes)==1, 'The settings dialog did not open'
    if outcomes[0] is not None:raise outcomes[0]


def check_settings_on_every_page(runtime, app, checks):
    from custom_card_data import normalize_cards
    from resource_options import CAPSULE_PAGES, DESKTOP_COMPONENTS, RESOURCE_PAGES
    from sticky_notes_store import normalize_notes

    service = runtime.resources
    w = service.window
    cfg = service.cfg
    overrides = {'resource_'+key:True for key in RESOURCE_PAGES if key != 'resources'}
    overrides.update(resource_component_locations=dict.fromkeys(DESKTOP_COMPONENTS, 'capsule'),
                     resource_expanded_width=640, resource_expanded_height=310, resource_auto_hide=False,
                     notes_enabled=True, notes_visible=True, clock_enabled=True, calendar_enabled=True,
                     daily_picture_enabled=True, sticky_notes=normalize_notes([dict(id='settings', text='测试')]),
                     custom_cards=normalize_cards([dict(id='settings', title='测试', rows=[dict(kind='text')])]))
    events = []
    class FormEvents(QObject):
        def eventFilter(self, obj, event):
            if (obj is w.detail and event.type()==QEvent.Hide) or (obj is w and event.type()==QEvent.Resize):
                events.append((w.page_key, event.type(), w.size()))
            return False

    with patch.dict(cfg, overrides):
        service.sync()
        if w._fold_surface:w._fold_surface.animation.setCurrentTime(w._fold_surface.animation.duration())
        probe = FormEvents()
        w.installEventFilter(probe)
        w.detail.installEventFilter(probe)
        try:
            for key in CAPSULE_PAGES:
                assert w.page_enabled(key), key
                w.page_buttons[key].click()
                app.processEvents()
                page = w.dashboard if key=='resources' else w.view(key)
                scroll = w.scroll if key=='resources' else page
                if key=='ai':scroll = page.statistics.scroll
                bar = scroll.verticalScrollBar()
                bar.setValue(min(4, bar.maximum()))
                position = bar.value()
                geometry = w.geometry()
                fold_state = (cfg['resource_collapsed'], service.auto_compact)
                events.clear()
                def check_page():
                    current = w.dashboard if key=='resources' else getattr(w, '_'+key+'_view')
                    assert current is page and page.isVisible() and w.detail.isVisible(), key
                    assert w.page_key==key and w.geometry()==geometry and not service.compact, key
                    assert bar.value()==position and w._fold_surface is None, key
                    assert (cfg['resource_collapsed'], service.auto_compact)==fold_state
                def inspect(dialog):
                    check_page()
                    if key=='weather':
                        dialog.fields['resource_delay'].setValue(4)
                        assert dialog.commit()
                        check_page()
                visit_options(w.settings_button.click, inspect)
                if key=='traffic':
                    runtime.tray.show_settings()
                    try:
                        check_page()
                        visit_options(lambda:service.settings(page=1), inspect)
                        check_page()
                    finally:runtime.tray.settings_dialog.reject()
                app.processEvents()
                check_page()
                assert not events, events
        finally:
            w.detail.removeEventFilter(probe)
            w.removeEventFilter(probe)
            w.select_page('weather')

        cfg['resource_auto_hide'] = True
        w.sync_auto_fold()
        def leave_during_settings(dialog):
            with patch.object(QCursor, 'pos', return_value=w.geometry().topLeft()-QPoint(40,40)):
                w.outside_since = None
                w.fold_idle()
                assert not service.compact and w.outside_since is not None
                w.outside_since -= cfg['resource_delay'] + 1
                w.fold_idle()
                assert service.compact
        visit_options(w.settings_button.click, leave_during_settings)
        assert service.compact and not w.detail.isVisible()
        service.fold(False, automatic=True)
    service.sync()
    checks.append(f'All {len(CAPSULE_PAGES)} capsule pages keep their geometry, visible widgets and scroll position through the actual Settings button. Main and nested settings and an unrelated save keep the active page. The usual pointer leave delay can still fold the capsule while editing.')


def run(api,runtime,app,output,checks):
    from resource_options import DEFAULTS
    from resource_redesign_tests import fixtures
    cfg=runtime.dock.cfg;before=copy.deepcopy(cfg);service=runtime.resources
    try:
        cfg.update(copy.deepcopy(DEFAULTS));cfg.update(resource_enabled=True,resource_ai=True,resource_music=True,resource_auto_hide=False,resource_collapsed=False)
        service.sync();w=service.window;bridge=service.deck
        bridge.accept(dict(type='ai',providers=fixtures()[:1]));w.select_page('ai');app.processEvents();stats=w.stats_view
        from resource_options import CAPSULE_PAGES
        assert set(w.page_buttons)==set(CAPSULE_PAGES) and w.page_buttons['ai'].text()=='AI'
        assert not w.page_enabled('news')
        assert stats.quotas.rows and stats.data['available'] and not stats.provider.isVisible() and not stats.note.isVisible()
        stats.notes_button.click();assert stats.note.isVisible();stats.notes_button.click();assert not stats.note.isVisible()
        w.grab().save(str(output/'tight-ai-single.png'))
        def event(handle,kind,global_pos):
            point=QPointF(handle.mapFromGlobal(global_pos));buttons=Qt.NoButton if kind==QEvent.MouseButtonRelease else Qt.LeftButton
            app.sendEvent(handle,QMouseEvent(kind,point,QPointF(global_pos),Qt.LeftButton,buttons,Qt.NoModifier))
        def drag(edge,delta):
            handle=w.resize_edges.handles[edge];start=handle.mapToGlobal(handle.rect().center());end=start+delta
            event(handle,QEvent.MouseButtonPress,start);event(handle,QEvent.MouseMove,end);app.processEvents()
            rect=w.geometry();w.refresh();w.reposition();assert w.geometry()==rect,'Sampling reset an active resize'
            event(handle,QEvent.MouseButtonRelease,end);app.processEvents();return rect
        with patch.object(service,'set_options',wraps=service.set_options) as saved:
            wanted=drag('rb',QPoint(90,75));assert saved.call_count==1
        assert cfg['resource_expanded_width']==wanted.width() and cfg['resource_expanded_height']==wanted.height()
        assert api.load_config()['resource_expanded_width']==wanted.width()
        for key in ('resources','music','ai'):w.select_page(key);app.processEvents();assert w.geometry()==wanted
        w.grab().save(str(output/'tight-ai-resized.png'))
        area=(QApplication.screenAt(w.geometry().center()) or QApplication.primaryScreen()).availableGeometry()
        drag('lt',QPoint(-2000,-2000));assert area.contains(w.geometry()) and w.width()<=1000 and w.height()<=800
        drag('rb',QPoint(-2000,-2000));assert w.width()==260 and w.height()==180
        service.fold(True);app.processEvents();drag('rb',QPoint(32,5));assert not cfg['resource_compact_auto_width']
        size=w.size();w.refresh();w.reposition();assert w.size()==size
        service.set_options(resource_enabled=False);service.set_options(resource_enabled=True);w=service.window;app.processEvents();assert w.size()==size
        old=w.geometry()
        with patch.object(service,'set_options',return_value=False):drag('rb',QPoint(30,5))
        assert w.geometry()==old,'Failed save left an unpersisted window size'
        from resource_settings import ResourceOptions
        options = ResourceOptions(service)
        options.show();app.processEvents()
        assert options.tabs.currentIndex() == 0 and 'resource_open_page' in options.fields
        preferred = options.fields['resource_open_page']
        preferred.setCurrentIndex(preferred.findData('weather'))
        assert preferred.isVisible() and options.grab().save(str(output/'open-page-settings.png'))
        options.tabs.setCurrentIndex(7)
        options.fields['resource_weather'].setChecked(True)
        assert options.commit() and api.load_config()['resource_open_page'] == 'weather'
        options.reject();options.deleteLater()
        with patch.object(QCursor, 'pos', return_value=w.geometry().center()):
            w.expand_hover()
        assert not service.compact and w.page_key == 'weather' and w.weather_view.isVisible()
        check_settings_on_every_page(runtime, app, checks)
        w.select_page('traffic')
        service.sync()
        assert w.page_key == 'traffic'
        assert service.set_options(resource_expand_mode='click') and service.fold(True)
        point = QPointF(w.rect().center())
        screen_point = QPointF(w.mapToGlobal(point.toPoint()))
        for kind, buttons in ((QEvent.MouseButtonPress, Qt.LeftButton), (QEvent.MouseButtonRelease, Qt.NoButton)):
            app.sendEvent(w, QMouseEvent(kind, point, screen_point, Qt.LeftButton, buttons, Qt.NoModifier))
        assert not service.compact and w.page_key == 'weather'
        assert service.set_options(resource_weather=False) and service.fold(True)
        service.open()
        assert not service.compact and w.page_key == 'resources' and service.extras is None
        from config_transfer import normalize
        old_profile = dict(api.DEFAULT_CONFIG, resource_notifications=True,
                           resource_compact_pinned=['cpu','notifications','weather'],
                           resource_compact_order=['notifications','weather','cpu'])
        old_profile.pop('resource_open_page')
        old_profile.pop('resource_content_scale')
        migrated = normalize(old_profile, api)
        assert migrated['resource_content_scale']==100
        assert 'resource_notifications' not in migrated
        assert migrated['resource_open_page'] == 'last'
        assert migrated['resource_compact_pinned'] == ['cpu','weather']
        assert migrated['resource_compact_order'] == ['weather','resources']
        checks.append('Capsule resize: sampling does not reset drag; single save, screen/min/max bounds, page geometry stable, manual compact size survives recreation, failed save restores. Unified AI, single-provider filter hidden, remarks collapsed.')
        checks.append('Capsule opening page: weather preference persists, hover and click open it, normal refresh preserves the selected page, disabled preference falls back to resources, and old reminder settings and pins migrate away.')
        from capsule_content_scale_tests import run as check_content_scale
        check_content_scale(api,runtime,app,output,checks)
    finally:cfg.clear();cfg.update(before);service.sync();api.save_config(cfg)
