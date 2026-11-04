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
    checks.append('taskbar text: follow/white/black normalization; fake registry preserves application theme; original/missing value restore, newer user override wins, crash recovery, disk/registry failure rollback, isolated no-op; text-only change does not restart background backend (no real Windows theme changed)')
