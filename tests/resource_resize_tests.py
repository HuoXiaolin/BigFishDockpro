"""Native resize persistence, unified AI and collapsed remarks."""
import copy
from unittest.mock import patch
from PyQt5.QtCore import Qt,QPoint,QPointF,QEvent
from PyQt5.QtGui import QCursor,QMouseEvent
from PyQt5.QtWidgets import QApplication

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
        w.select_page('traffic')
        service.sync()
        assert w.page_key == 'traffic'
        service.set_main_settings(True)
        assert service.compact
        service.set_main_settings(False)
        assert not service.compact and w.page_key == 'traffic'
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
        migrated = normalize(old_profile, api)
        assert 'resource_notifications' not in migrated
        assert migrated['resource_open_page'] == 'last'
        assert migrated['resource_compact_pinned'] == ['cpu','weather']
        assert migrated['resource_compact_order'] == ['weather','cpu']
        checks.append('Capsule resize: sampling does not reset drag; single save, screen/min/max bounds, page geometry stable, manual compact size survives recreation, failed save restores. Unified AI, single-provider filter hidden, remarks collapsed.')
        checks.append('Capsule opening page: weather preference persists, hover and click open it, normal refresh and temporary settings fold preserve the selected page, disabled preference falls back to resources, and old reminder settings and pins migrate away.')
    finally:cfg.clear();cfg.update(before);service.sync();api.save_config(cfg)
