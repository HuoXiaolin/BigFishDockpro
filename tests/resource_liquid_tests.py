"""Native liquid, face and weather checks, exclusively on the private desktop."""
import copy
import ctypes
import time
from types import SimpleNamespace
from unittest.mock import patch
from PyQt5.QtCore import Qt,QPoint,QPointF,QRect,QRectF,QEvent
from PyQt5.QtGui import QMouseEvent,QImage,QPainter,QColor
from PyQt5.QtWidgets import QApplication


def run(api,runtime,app,output,checks):
    from run_isolated_test import assert_isolated
    assert_isolated()
    from resource_options import DEFAULTS
    from resource_liquid import attached,nearest
    from resource_weather import forecast,clean_cities,DEFAULT_CITIES
    from card_snap import snap_target
    from resource_face import PetFace
    cfg=runtime.dock.cfg;before=copy.deepcopy(cfg);service=runtime.resources
    def pump(seconds):
        until=time.monotonic()+seconds
        while time.monotonic()<until:app.processEvents();time.sleep(.005)
    def event(w,kind,pos,global_pos):
        buttons=Qt.NoButton if kind==QEvent.MouseButtonRelease else Qt.LeftButton
        app.sendEvent(w,QMouseEvent(kind,QPointF(pos),QPointF(global_pos),Qt.LeftButton,buttons,Qt.NoModifier))
    try:
        cfg.update(copy.deepcopy(DEFAULTS));cfg.update(resource_enabled=True,resource_auto_hide=False,resource_collapsed=True,card_snap=True,card_snap_distance=12,
            resource_face=True,resource_edge_snap=True,resource_live_glass=True,resource_weather=True,
            resource_background='custom',resource_appearance=dict(material='liquid',theme='light',color='',opacity=48,blur=8,highlight=45))
        service.sync();w=service.window;extra=service.extras;app.processEvents()
        assert extra and extra.weather_job is None
        assert not w.liquid.live.job and w.liquid.watch.isActive()
        area=(QApplication.screenAt(w.geometry().center()) or QApplication.primaryScreen()).availableGeometry()
        demo_area = QRect(-500, 0, 1000, 650)
        middle = QRect(-100, 200, 100, 65)
        assert snap_target(middle, demo_area, [], 12) is None
        assert snap_target(middle, demo_area, [QRect(13, 230, 90, 100)], 12) is None
        assert snap_target(middle, demo_area, [QRect(12, 230, 90, 100)], 12) == (middle.translated(12, 0), 'free')
        assert snap_target(middle, demo_area, [QRect(8, 500, 90, 100)], 12) is None
        assert snap_target(middle.translated(0, -193), demo_area, [], 12)[1] == 'top'
        for edge in ('top','bottom','left','right'):
            rect=attached(QRect(area.center().x()-w.width()//2,area.center().y()-22,w.width(),44),area,edge)
            assert nearest(rect,area)==edge
            w.press=QPoint();w.setGeometry(rect);w.press=None;w.liquid.drop(rect.center());pump(.3)
            assert not w.liquid.landing and cfg['resource_edge']==edge and w.geometry()==attached(w.geometry(),area,edge)
            service.fold(False);assert w.geometry()==attached(w.geometry(),area,edge)
            expanded=w.geometry();w.select_page('resources');assert w.geometry()==expanded
            service.fold(True);assert w.geometry()==attached(w.geometry(),area,edge)
            if edge=='top':w.grab().save(str(output/'liquid-attached-top.png'))
        service.set_options(resource_edge='top');pump(.04)
        start=w.mapToGlobal(QPoint(65,20));event(w,QEvent.MouseButtonPress,QPoint(65,20),start)
        event(w,QEvent.MouseMove,QPoint(65,20),start+QPoint(0,40));app.processEvents()
        assert w.liquid.bridge and w.liquid.bridge.isVisible() and not w.liquid.bridge.path.isEmpty()
        w.liquid.bridge.grab().save(str(output/'liquid-tether.png'));assert w.liquid.down
        w.grab().save(str(output/'liquid-pressed.png'))
        event(w,QEvent.MouseMove,QPoint(65,20),start+QPoint(0,120));app.processEvents()
        assert w.liquid.broken and w.liquid.bridge.timer.isActive()
        w.liquid.bridge.grab().save(str(output/'liquid-drip.png'))
        event(w,QEvent.MouseButtonRelease,QPoint(65,20),start+QPoint(0,120));pump(.3)
        assert not w.liquid.bridge.isVisible() and not w.liquid.down
        # A disabled snap retains normal placement; a failed save restores it.
        old=copy.deepcopy(cfg['resource_layout']);old_edge=cfg['resource_edge'];old_rect=w.geometry()
        with patch.object(service,'set_options',return_value=False):
            w.move(area.center().x()-w.width()//2,area.top()+5);assert w.liquid.drop(w.geometry().center())
        assert cfg['resource_layout']==old and cfg['resource_edge']==old_edge and w.geometry()==old_rect
        service.set_options(motion_enabled=False);assert not w.liquid.watch.isActive() and not w.liquid.frames.isActive()
        w.move(w.x(),w.y()+30);w.liquid.drop(w.geometry().center());assert not w.liquid.landing
        # Seven vector expressions, both app themes, no widget/layout changes.
        montage=QImage(7*90,144,QImage.Format_ARGB32_Premultiplied);montage.fill(Qt.transparent);p=QPainter(montage);p.setRenderHint(QPainter.Antialiasing)
        for row,light in enumerate((True,False)):
            p.fillRect(0,row*72,630,72,QColor('#f3f7fa' if light else '#202532'))
            for i,mood in enumerate(PetFace.MOODS):
                face=PetFace();face.mood=mood;face._near=True;face.blink_at=time.monotonic()+100
                for _ in range(70):face._t=time.monotonic()-.05;face._step(QPointF(),True,.9)
                colors=dict(ink='#172836' if light else '#e1edf3',light=light)
                face.paint(p,i*90+45,row*72+31,.9,1,QPointF(),True,colors)
                p.setPen(QColor(colors['ink']));p.drawText(QRect(i*90,row*72+51,90,17),Qt.AlignCenter,mood)
        p.end();montage.save(str(output/'liquid-seven-faces.png'))
        service.set_options(motion_enabled=True,resource_face=False,resource_halo=False)
        assert not w.liquid.watch.isActive() and not w.liquid.frames.isActive() and not w.animation.isActive()
        # Known cities do not need geocoding. Only a bounded forecast is retained.
        queries=[]
        def lookup(url):
            queries.append(url)
            return dict(current=dict(temperature_2m=16,weather_code=2,relative_humidity_2m=40,wind_speed_10m=8,time='2026-11-07T14:00'),
                daily=dict(time=['2026-11-07','2026-11-08','2026-11-09'],temperature_2m_min=[6,7,8],temperature_2m_max=[17,18,19],weather_code=[2,0,61]))
        extra.weather=[forecast(name,lookup) for name in DEFAULT_CITIES]
        assert len(queries)==3 and all('timezone=auto' in q for q in queries) and extra.weather[1]['name']=='乌鲁木齐'
        assert all('forecast_days=7' in q and 'past_days=1' in q for q in queries)
        def weekly(url):
            result=lookup(url);result['daily']={key:(values*3)[:7] for key,values in result['daily'].items()};return result
        assert len(forecast('天津',weekly)['days'])==7
        assert clean_cities(['天津','天津',' 沈阳 '])==['天津','沈阳']
        try:clean_cities(['天津']*7,True);raise AssertionError('Oversized city list accepted')
        except ValueError:pass
        service.fold(False);w.select_page('weather');pump(.03)
        assert not w.weather_view.notes.isVisible();w.grab().save(str(output/'liquid-weather.png'))
        service.fold(True);w.offset=0;seen=set()
        for page in range(12):w.offset=page;w.grab();seen.update(w.compact_shown)
        assert 'weather' in seen
        # A bounded synthetic background exercises the actual material renderer.
        live=w.liquid.live
        one=QImage(64,8,QImage.Format_ARGB32_Premultiplied);one.fill(QColor('#d14455'));live.image=one;live.revision+=1;first=w.grab().toImage()
        two=QImage(64,8,QImage.Format_ARGB32_Premultiplied);two.fill(QColor('#2660ba'));live.image=two;live.revision+=1;second=w.grab().toImage()
        assert first!=second and live.image.byteCount()<=64*8*4
        second.save(str(output/'liquid-live-material.png'))
        # Large panels cache the background at half resolution. The four
        # margins must stay transparent and the far side must still be filled.
        service.set_options(resource_expanded_width=501, resource_expanded_height=321,
                            resource_edge='free', resource_halo=True)
        service.fold(False)
        w.select_page('resources')
        live.image = two
        live.revision += 1
        expanded_glass = w.grab().toImage()
        cache = w.glass.image.toImage()
        expanded_glass.save(str(output/'liquid-expanded-clip.png'))
        assert cache.width() == round(w.width() * w.devicePixelRatioF() / 2)
        for image in (cache, expanded_glass):
            width, height = image.width(), image.height()
            rim = [(0, height//2), (width-1, height//2), (width//2, 0), (width//2, height-1)]
            alpha = [image.pixelColor(x, y).alpha() for x, y in rim]
            assert alpha == [0, 0, 0, 0], (image.size(), alpha)
            assert image.pixelColor(width*3//4, height*3//4).alpha() > 240
        service.fold(True)
        # Affinity is restored even when a capture fails; no actual screen read.
        import resource_live_glass as lg
        import resource_glass_capture as gc
        class Call:
            def __init__(self,fn):self.fn=fn
            def __call__(self,*args):return self.fn(*args)
        calls=[]
        def get(hwnd,ptr):ptr._obj.value=1;return True
        user=SimpleNamespace(GetWindowDisplayAffinity=Call(get),SetWindowDisplayAffinity=Call(lambda hwnd,value:calls.append(value) or True))
        fake=SimpleNamespace(windll=SimpleNamespace(user32=user),byref=ctypes.byref,POINTER=ctypes.POINTER)
        with patch.object(lg,'C',fake),patch.object(gc,'grab_tiny',side_effect=OSError('fixture')):
            try:lg.behind(123,(0,0,100,100),(10,10))
            except OSError:pass
        assert calls==[0x11,1]
        service.set_options(resource_face=True,resource_halo=True);pump(.04)
        assert w.animation.isActive() and w.clock_tick.isActive()
        w.hide();app.processEvents()
        assert not w.liquid.watch.isActive() and not w.liquid.frames.isActive() and not live.timer.isActive() and live.image is None
        assert not extra.weather_timer.isActive()
        assert not w.animation.isActive() and not w.clock_tick.isActive() and not w.rotate.isActive()
        w.show();pump(.04);assert extra.weather_timer.isActive() and w.animation.isActive() and w.clock_tick.isActive()
        w.move(w.x()+30,w.y()+30);w.liquid.drop(w.geometry().center())
        service.set_options(motion_enabled=False)
        assert not w.liquid.landing and w.geometry()==attached(w.geometry(),area,cfg['resource_edge'])
        service.set_options(resource_weather=False);assert service.extras is None and not extra.weather_timer.isActive()
        service.set_options(resource_enabled=False);assert service.extras is None and not w.liquid.watch.isActive()
        checks.append('Liquid capsule: four-edge snap and fold anchoring, finite tether/drip, failed-save restore, animation-off, seven vector moods in both themes, bounded live material, transparent margins at half-resolution, and capture-affinity restore on failure; hide/disable stop all workers/timers. Private desktop only; live GDI background capture not exercised.')
        checks.append('Weather: Tianjin/Urumqi/Shenyang, Beijing time and three-day parsing, city validation, compact paging, pause when hidden and stop when disabled.')
    finally:cfg.clear();cfg.update(before);service.sync();api.save_config(cfg)
