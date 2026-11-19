"""Taskbar text ownership/failure checks using fake registry IO only."""
import tempfile
from pathlib import Path
from unittest.mock import Mock,patch
from types import SimpleNamespace

def run(output,checks):
    from taskbar_text import TaskbarText
    from taskbar_appearance import TaskbarAppearance
    from feature_config import normalize
    assert normalize({})['taskbar_text_mode']=='system'
    assert normalize({'taskbar_text_mode':'red'})['taskbar_text_mode']=='system'
    assert normalize({})['taskbar_text_auto'] is False
    assert normalize({'taskbar_text_auto':'false'})['taskbar_text_auto'] is False
    from taskbar_text import background_mode
    from background_contrast import foreground, wallpaper_color
    assert foreground('#ffffff') == '#000000' and foreground('#000000') == '#ffffff'
    auto = {'taskbar_text_auto':True, 'taskbar_text_mode':'dark', 'taskbar_mode':'clear'}
    assert background_mode(auto, (240,240,240)) == 'dark'
    assert background_mode(auto, (12,18,24)) == 'light'
    assert background_mode(auto, None, previous='light') == 'light'
    assert background_mode(auto, None) == 'system'
    auto.update(taskbar_mode='color', taskbar_color='#ffffff', taskbar_opacity=100)
    assert background_mode(auto, (0,0,0)) == 'light'
    auto['taskbar_mode']='system'
    assert background_mode(auto, (0,0,0)) == 'system'
    auto['taskbar_text_auto']=False
    assert background_mode(auto, (0,0,0)) == 'dark'
    from PyQt5.QtCore import QRect, QRectF, QPoint
    from PyQt5.QtGui import QColor, QGuiApplication, QImage, QPainter
    from taskbar_surface import composed_color
    main = SimpleNamespace(name=lambda:'Primary', geometry=lambda:QRect(0,0,800,600))
    secondary = SimpleNamespace(name=lambda:'Second', geometry=lambda:QRect(-1280,0,1280,720))
    window = SimpleNamespace(screen=lambda:secondary, mapToGlobal=lambda _:QPoint(-1280,0))
    primary_bar = dict(hwnd=81, screen='Primary', rect=QRect(0,560,800,40))
    secondary_bar = dict(hwnd=82, screen='Second', rect=QRect(-1280,680,1280,40))
    with tempfile.TemporaryDirectory(prefix='bfp-taskbar-wallpaper-') as folder:
        path = Path(folder)/'bands.png'
        bands = QImage(160, 90, QImage.Format_RGB32)
        bands.fill(QColor('white'))
        painter = QPainter(bands)
        painter.fillRect(0, 80, 160, 10, QColor('black'))
        painter.end()
        assert bands.save(str(path))
        wide = (-1920, 0, 1920, 1080)
        shared = (-1920, 0, 2720, 1080)
        primary_key = ('', None, 2, QColor('white').rgba(), main.geometry().getRect(), shared)
        second_key = (str(path), path.stat().st_mtime_ns, 2, QColor('white').rgba(), wide, shared)
        def wallpaper_key(handle, screen):
            if screen is main:
                assert handle == 81
                return primary_key
            assert screen is secondary and (handle == 82 or handle is window)
            return second_key
        with patch('resource_taskbar.taskbars', return_value=[primary_bar, secondary_bar]) as bars, \
             patch('wallpaper_source.wallpaper_key', side_effect=wallpaper_key), \
             patch.object(QGuiApplication,'screens',return_value=[main,secondary]), \
             patch('taskbar_surface.composed_color', side_effect=AssertionError('Taskbar read screen pixels')):
            assert wallpaper_color(window) == (0,0,0)
            bars.assert_called_once_with(include_hidden=True)
            secondary_bar['rect'] = QRect(-1280,719,1280,40)
            assert wallpaper_color(window) == (0,0,0)
            secondary_bar['rect'] = QRect(-1280,-39,1280,40)
            assert wallpaper_color(window) == (255,255,255)
            assert wallpaper_color(window, QRectF(0,0,20,20)) == (255,255,255)
            bars.return_value = [primary_bar]
            assert wallpaper_color(window) == (255,255,255)
            bars.return_value = []
            assert wallpaper_color(window) is None
    # The Start and notification panels still use the composed surface reader.
    points = [(-1850+i*140,1040) for i in range(9)]
    user, gdi = Mock(), Mock()
    user.GetDC.return_value = 123
    user.MonitorFromPoint.return_value = 1
    gdi.CreateCompatibleDC.return_value = 456
    gdi.SelectClipRgn.return_value = 2
    gdi.GetPixel.side_effect = [0xffffff]*7 + [0,0xffffffff]
    with patch('taskbar_surface._bindings',return_value=(user,gdi)):
        assert composed_color(points)==(255,255,255)
        assert all(-1920<point.x<0 and 1020<point.y<1080 for point,_ in (c.args for c in user.MonitorFromPoint.call_args_list))
        assert gdi.BitBlt.call_count==1 and all(c.args[0]==456 for c in gdi.GetPixel.call_args_list)
        gdi.DeleteDC.assert_called_once_with(456)
        user.ReleaseDC.assert_called_once_with(None,123)
        gdi.BitBlt.return_value=0
        gdi.GetPixel.reset_mock(side_effect=True)
        gdi.GetPixel.return_value=0xffffffff
        assert composed_color(points) is None
        assert all(c.args[0]==123 for c in gdi.GetPixel.call_args_list)
    for original in (None,0,1):
        with tempfile.TemporaryDirectory(prefix='bfp-taskbar-theme-') as folder:
            path=Path(folder)/'restore.json';state={'system':original,'apps':1};events=[]
            def write(value):state['system']=value;events.append(value)
            controller=TaskbarText(path,lambda _:None,read=lambda:state['system'],write=write,notify=lambda:None)
            assert controller.sync('system') and not events and not path.exists()
            assert controller.sync('light') and state['system']==0
            count=len(events);assert controller.sync('light') and len(events)==count
            assert controller.sync('dark') and state['system']==1
            controller.close();assert state=={'system':original,'apps':1} and not path.exists()
    with tempfile.TemporaryDirectory(prefix='bfp-taskbar-restore-') as folder:
        path=Path(folder)/'restore.json';state=[1];events=[]
        def write(value):state[0]=value;events.append(value)
        make=lambda:TaskbarText(path,lambda _:None,read=lambda:state[0],write=write,notify=lambda:None)
        controller=make();assert controller.sync('light') and state[0]==0
        # Startup after a simulated crash restores exactly the journaled value.
        resumed=make();assert resumed.sync('system') and state[0]==1 and not path.exists()
        controller=make();controller.sync('light');state[0]=1;count=len(events)
        controller.close();assert state[0]==1 and len(events)==count and not path.exists()
        controller=make()
        with patch.object(controller,'persist',side_effect=OSError('disk denied')):
            assert not controller.sync('light') and state[0]==1
        assert controller.sync('light') and state[0]==0
        previous=path.read_text()
        with patch.object(controller,'write',side_effect=OSError('registry denied')):
            assert not controller.sync('dark') and state[0]==0 and path.read_text()==previous
        controller.close();assert state[0]==1
        io=Mock();disabled=TaskbarText(path,io,enabled=False,read=io,write=io,notify=io)
        disabled.sync('light');disabled.close();assert not io.called
    # Foreground selection is independent of background effects and doesn't restart TTB.
    cfg={'taskbar_mode':'clear','taskbar_color':'#85c6ed','taskbar_opacity':32,'taskbar_blur':12,'taskbar_text_mode':'system'}
    component=TaskbarAppearance.__new__(TaskbarAppearance);component.dock=SimpleNamespace(cfg=cfg)
    component.text=Mock();component.xaml=Mock();component.backend=component.xaml
    component.sync();cfg['taskbar_text_mode']='light';component.sync()
    assert component.xaml.sync.call_count==1 and component.text.sync.call_count==2
    cfg['taskbar_text_auto']=True
    with patch('background_contrast.wallpaper_color',return_value=(255,255,255)), \
         patch('taskbar_surface.composed_color',side_effect=AssertionError('Taskbar sampled foreground pixels')):
        component.sync()
    assert component.text.sync.call_args.args==('dark',) and component.xaml.sync.call_count==1
    with patch('background_contrast.wallpaper_color',return_value=(8,8,8)):
        component.sync()
    assert component.text.sync.call_args.args==('light',) and component.xaml.sync.call_count==1
    component.text.selection='light'
    with patch('background_contrast.wallpaper_color',side_effect=OSError):
        component.sync()
    assert component.text.sync.call_args.args==('light',)
    checks.append('Taskbar automatic text: wallpaper-only contrast for the taskbar monitor, real image strips on a mixed-DPI secondary display, auto-hide, primary fallback, modes and last good color.')
    checks.append('taskbar text: follow/white/black normalization; fake registry preserves application theme; original/missing value restore, newer user override wins, crash recovery, disk/registry failure rollback, isolated no-op; text-only change does not restart background backend (no real Windows theme changed)')
