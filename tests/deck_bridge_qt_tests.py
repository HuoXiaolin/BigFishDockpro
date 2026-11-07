"""The real helper through Qt's pipe, without querying accounts or controlling media."""
import json,time
from unittest.mock import patch
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from PyQt5.QtCore import QObject,QProcess


def run(app,output,checks):
    from resource_deck import DeckBridge
    from resource_options import DEFAULTS
    class Owner(QObject):
        def __init__(self,root):
            super().__init__();self.cfg=dict(DEFAULTS,resource_enabled=True,resource_music=True,resource_ai=False,resource_lyrics=False)
            self.runtime=SimpleNamespace(dock=SimpleNamespace(preview=False),api=SimpleNamespace(CONFIG_DIR=root))
            self.window=None;self.messages=0
        def display(self):self.messages+=1
    with TemporaryDirectory(prefix='bigfish-qt-deck-') as root:
        owner=Owner(root);bridge=DeckBridge(owner);process=bridge.process
        try:
            with patch('deck_runtime.installed_runtime',return_value=None),patch.object(process,'start') as start:
                bridge.configure();bridge.refresh();assert not start.called and '.NET 10' in bridge.status
            bridge.configure();deadline=time.monotonic()+18
            while time.monotonic()<deadline and not bridge.media:
                app.processEvents();time.sleep(.02)
            assert bridge.media and owner.messages,'Qt pipe did not receive the media snapshot: '+bridge.status
            assert not bridge.providers and process.state()==QProcess.Running
            result=dict(passed=True,qt_pipe=True,ai_disabled=True,media_snapshots=owner.messages,
                        players=len(bridge.media.get('tracks') or []),helper_running=True)
        finally:
            bridge.close()
            if process.state()!=QProcess.NotRunning and not process.waitForFinished(3500):process.kill();process.waitForFinished(2000)
        assert process.state()==QProcess.NotRunning and process.exitCode()==0
        result['clean_exit']=True
        (output/'deck-qt-pipe.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        checks.append('Real AI/media helper: launched via Qt JSON pipe from the active source/bundle path, received media snapshots with AI/lyrics disabled, and exited cleanly. No playback controls or account queries executed.')
