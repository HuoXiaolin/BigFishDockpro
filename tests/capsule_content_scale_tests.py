"""Check content scaling on the actual capsule without changing its native bounds."""
from unittest.mock import patch

from PyQt5.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, Qt
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtWidgets import QApplication


def click_at(widget, point):
    screen=QPointF(widget.mapToGlobal(point))
    for event,held in ((QEvent.MouseButtonPress,Qt.LeftButton),(QEvent.MouseButtonRelease,Qt.NoButton)):
        QApplication.sendEvent(widget,QMouseEvent(event,QPointF(point),screen,Qt.LeftButton,held,Qt.NoModifier))


def run(api, runtime, app, output, checks):
    from capsule_order import PageTurns
    from resource_compact import plan
    from resource_options import CAPSULE_CONTENT_SCALE_RANGE, page_columns
    from resource_runner import capsule_rect
    from resource_settings import ResourceOptions
    from settings_sections import SIZE

    service=runtime.resources
    cfg=service.cfg
    settings=dict(resource_enabled=True, resource_collapsed=True, resource_auto_hide=False, motion_enabled=False,
                  resource_expand_mode='click', resource_fold='pill', resource_compact_auto_width=False,
                  resource_face=True, resource_face_scale=100, resource_runner_enabled=True, resource_runner_animal='penguin',
                  resource_compact_width=520, resource_compact_height=48, resource_compact_badge_height=20,
                  resource_expanded_width=500, resource_expanded_height=300, resource_clock=True, resource_clock_format='seconds',
                  resource_compact_order=['face','runner','weather','resources','clock'], resource_compact_zones={'weather':'center'},
                  resource_alert_almanac=False,resource_alert_volume=True,resource_content_scale=100)
    readings=[('weather','滨海新区','8℃',dict(temperature=8,code=2)),('cpu','CPU','28%','')]
    try:
        with patch.dict(cfg,settings),patch('resource_compact.compact_values',return_value=readings), \
                patch('resource_compact.compact_badges',return_value=([],0)),patch('resource_compact.status_values',return_value=[]):
            service.sync()
            w=service.window
            w.page_turns=PageTurns()
            w.grab()
            original=w.geometry()
            measured=[]
            for percent in (70,100,160):
                cfg['resource_content_scale']=percent
                w.sync_window()
                image=w.grab()
                weather=dict(zip(w.compact_shown,w.compact_bounds))['weather']
                runner=capsule_rect(w)
                assert w.geometry()==original and abs(weather.height()-20*percent/100)<1
                assert abs(weather.center().x()-w.rect().center().x())<2 and w.runner_at(runner.center())
                face=w.liquid.face_bounds
                assert face and w.rect().contains(face) and not runner.intersects(face)
                measured.append((runner.width(),face.width(),weather.width()))
                assert image.save(str(output/f'capsule-content-{percent}.png'))
            assert all(a<b<c for a,b,c in zip(*measured)),measured

            # Read the painted layer, including device badges that briefly extend to show text.
            from capsule_scale import window_rect
            indicators=service.indicators
            with patch.object(indicators,'selected',('volume',)),patch.object(indicators,'values',{'volume':(42,False)}), \
                    patch.object(indicators,'transitions',{}),patch.object(indicators,'clock',return_value=10.), \
                    patch.dict(cfg,resource_compact_order=['volume'],resource_compact_zones={'volume':'center'}):
                for percent in (70,100,160):
                    cfg['resource_content_scale']=percent
                    for changed in (False,True):
                        indicators.transitions={'volume':(9.,0.,'42')} if changed else {}
                        w._compact_cache=None
                        w.grab()
                        placed=plan(w,w.width())['positions']['volume']
                        _,side,width,label=placed.data
                        assert (width>side) if changed else (width==side)
                        assert label==('42' if changed else '')
                        _,_,layer,_=w._compact_surface
                        symbol=QPointF(placed.x+side/2,w.height()/(2*percent/100))
                        # The left interior of the badge must line up with the physical center group even below 100% DPI.
                        pixel=((symbol-QPointF(side/3,0))*layer.devicePixelRatioF()).toPoint()
                        assert layer.toImage().pixelColor(pixel).alpha()>0
                        box=window_rect(w,QRectF(placed.x,0,width,side))
                        assert abs(box.center().x()-w.rect().center().x())<2

            for shape in ('pill','bar','ball'):
                cfg.update(resource_fold=shape,resource_compact_auto_width=True)
                sizes=[]
                for percent in (100,160,70):
                    cfg['resource_content_scale']=percent
                    w.sync_window();w.grab()
                    sizes.append(w.geometry())
                assert sizes[0]==sizes[1]==sizes[2],(shape,sizes)
            cfg.update(resource_fold='pill',resource_compact_auto_width=False,resource_compact_width=96,
                       resource_compact_height=28,resource_content_scale=160)
            w.sync_window()
            layout=plan(w,w.width())
            visible=set()
            for _ in range(len(layout['pages'])):
                w.grab()
                visible.update(plan(w,w.width())['positions'])
                w.shift_compact_page(1)
            assert {'face','runner','weather','resources','clock'}<=visible,visible

            cfg.update(resource_collapsed=False,resource_compact_width=520)
            service.auto_compact=None
            w.sync_window()
            w.select_page('resources')
            initial=w.geometry()
            dialog=ResourceOptions(service)
            try:
                dialog.tabs.setCurrentIndex(SIZE)
                dialog.show()
                app.processEvents()
                field=dialog.fields['resource_content_scale']
                assert (field.minimum(),field.maximum())==CAPSULE_CONTENT_SCALE_RANGE
                field.setValue(75)
                assert dialog.grab().save(str(output/'capsule-content-settings.png'))
                dialog.reject()
                assert cfg['resource_content_scale']==160
            finally:
                dialog.deleteLater()
            for percent in (70,160,100):
                dialog=ResourceOptions(service)
                try:
                    dialog.show_page(SIZE)
                    dialog.fields['resource_content_scale'].setValue(percent)
                    assert dialog.commit()
                finally:
                    dialog.deleteLater()
                app.processEvents()
                assert api.load_config()['resource_content_scale']==percent
                assert w.geometry()==initial and w.page_key=='resources'
                assert page_columns(w)==(1 if percent==160 else 2)
                assert w.grab().save(str(output/f'capsule-expanded-{percent}.png'))
                if percent!=100:
                    view=w.scaled_detail
                    assert abs(view.transform().m11()-percent/100)<.001
                    button=w.rank_buttons['memory' if percent==70 else 'cpu']
                    w.scroll.ensureWidgetVisible(button,2,2)
                    app.processEvents()
                    pos=button.mapTo(w.detail,button.rect().center())
                    point=view.mapFromScene(QPointF(pos))
                    assert view.viewport().rect().contains(point),(percent,point,view.sceneRect(),view.viewportTransform().dy(),w.scroll.verticalScrollBar().value())
                    click_at(view.viewport(),point)
                    assert w.rank_by==('memory' if percent==70 else 'cpu')
                else:
                    assert w.scaled_detail is None and w.detail.parentWidget() is w
            checks.append('Capsule content 70/100/160%: saved and cancelled settings, measured weather, face and pet, mapped pet and dashboard clicks, narrow paging and stable native sizes for all three shapes and expanded pages.')
            from custom_card_data import normalize_cards
            from capsule_scale import widget_rect
            from resource_options import CAPSULE_PAGES, DESKTOP_COMPONENTS, RESOURCE_PAGES
            from sticky_notes_store import normalize_notes
            cfg.update({'resource_'+key:True for key in RESOURCE_PAGES if key!='resources'})
            cfg.update(resource_content_scale=145,resource_component_locations=dict.fromkeys(DESKTOP_COMPONENTS,'capsule'),
                       clock_enabled=True,calendar_enabled=True,notes_enabled=True,notes_visible=True,daily_picture_enabled=True,
                       sticky_notes=normalize_notes([{'id':'scale','text':'测试'}]),
                       custom_cards=normalize_cards([{'id':'scale','title':'测试','rows':[{'kind':'text'}]}]))
            service.sync()
            for key in CAPSULE_PAGES:
                assert w.page_enabled(key),key
                w.select_page(key)
                app.processEvents()
                assert w.geometry()==initial and not w.grab().isNull(),key
                if key=='weather':
                    city=w.weather_view.city
                    if city.count()<2:
                        city.clear()
                        city.addItems(['天津市 · 武清区','天津市 · 滨海新区'])
                    city.setEnabled(True)
                    city.showPopup()
                    app.processEvents()
                    popup=city.view()
                    index=city.model().index(1,0)
                    assert popup.isVisible() and popup.visualRect(index).isValid()
                    anchor=widget_rect(w,city,city.rect()).translated(w.mapToGlobal(QPoint())).toAlignedRect()
                    frame=city._popup
                    proxy=frame.graphicsProxyWidget()
                    if proxy:
                        viewport=w.scaled_detail.viewport()
                        physical=w.scaled_detail.mapFromScene(proxy.sceneBoundingRect()).boundingRect().translated(viewport.mapToGlobal(QPoint()))
                        row=popup.viewport().mapTo(frame,popup.visualRect(index).center())
                        target=w.scaled_detail.mapFromScene(proxy.mapToScene(QPointF(row)))
                        assert viewport.rect().contains(target),(anchor,physical,target)
                    else:
                        physical=QRect(frame.mapToGlobal(QPoint()),frame.size())
                        viewport=popup.viewport()
                        target=popup.visualRect(index).center()
                    assert abs(physical.left()-anchor.left())<=3 and min(abs(physical.top()-anchor.bottom()),abs(physical.bottom()-anchor.top()))<=8,(anchor,physical)
                    click_at(viewport,target)
                    assert city.currentIndex()==1
            checks.append('Rendered all expanded capsule pages at 145%, including hosted notes, clock, almanac, daily picture and custom card; selected a city from the weather menu.')
            cfg.update(resource_expanded_width=550,resource_expanded_height=335)
            w.sync_window()
            assert (w.width(),w.height(),cfg['resource_content_scale'])==(550,335,145)
    finally:
        service.sync()
        api.save_config(cfg)
