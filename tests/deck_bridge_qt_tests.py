"""The real helper through Qt's pipe, without querying accounts or controlling media."""
import json,time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from PyQt5.QtCore import QObject,QProcess,QProcessEnvironment


def local_usage_environment(root):
    sessions = Path(root) / 'pi-sessions'
    sessions.mkdir()
    entry = dict(type='usage', id='fixture', timestamp=datetime.now().astimezone().isoformat(),
                 model='fixture', usage=dict(input=10, output=3, cacheRead=2, cacheWrite=1, cost=dict(total=.0125)))
    (sessions / 'usage.jsonl').write_text(json.dumps(entry) + '\n', encoding='utf-8')
    env = QProcessEnvironment.systemEnvironment()
    env.insert('PI_CODING_AGENT_SESSION_DIR', str(sessions))
    # Keep this child offline, including the optional public pricing refresh.
    env.insert('HTTPS_PROXY', 'http://127.0.0.1:1')
    env.insert('NO_PROXY', '')
    return env


def run(app,output,checks):
    from resource_deck import DeckBridge
    from resource_options import DEFAULTS
    from resource_processes import ProcessRanking
    class Owner(QObject):
        def __init__(self,root):
            super().__init__();self.cfg=dict(DEFAULTS,resource_enabled=True,resource_music=True,resource_ai=False,resource_lyrics=False)
            self.runtime=SimpleNamespace(dock=SimpleNamespace(preview=False),api=SimpleNamespace(CONFIG_DIR=root))
            self.window=None;self.messages=0;self.sounds=[]
        def display(self):self.messages+=1
        def play_reminder_sound(self,kind):self.sounds.append(kind)
    with TemporaryDirectory(prefix='bigfish-qt-deck-') as root:
        owner=Owner(root);bridge=DeckBridge(owner);process=bridge.process
        try:
            owner.cfg['resource_quota_alert'] = True
            for percent, stale, expected in ((90,False,0),(30,True,0),(85,False,0),(35,False,0),(65,False,1),(90,False,2)):
                bridge.local_providers = [dict(id='fixture', name='Fixture', stale=stale, quotas=[{'percent': percent}])]
                bridge.provider_rows_changed()
                assert owner.sounds == ['quota'] * expected
            checks.append('AI quota: first low read and stale updates are silent, new threshold crossings still alert.')
            with patch('deck_runtime.installed_runtime',return_value=None),patch.object(process,'start') as start:
                bridge.configure();bridge.refresh();assert not start.called and '.NET 10' in bridge.status
            owner.cfg.update(resource_ai=True, resource_ai_providers=['Pi'])
            with patch.object(QProcessEnvironment, 'systemEnvironment', return_value=local_usage_environment(root)):
                bridge.configure()
            deadline=time.monotonic()+20
            while time.monotonic()<deadline and not (bridge.media and bridge.providers):
                app.processEvents();time.sleep(.02)
            assert bridge.media and owner.messages,'Qt pipe did not receive the media snapshot: '+bridge.status
            assert process.state()==QProcess.Running
            assert [row['id'] for row in bridge.providers] == ['Pi'], 'Qt pipe did not receive local usage: '+bridge.ai_status
            provider = bridge.providers[0]
            usage = provider['week']
            assert provider['usageAvailable'] and provider['usageComplete']
            assert (usage['tokens'], usage['records'], usage['cost']) == (16, 1, .0125), usage
            pid = int(process.processId())
            rows = ProcessRanking().snapshot()
            assert pid in rows
            consoles = sum(row.parent == pid and row.name.casefold() in ('conhost', 'openconsole') for row in rows.values())
            assert consoles == 0, 'The bridge started a console host'
            result=dict(passed=True,qt_pipe=True,usage=usage,media_snapshots=owner.messages,
                        players=len(bridge.media.get('tracks') or []),helper_running=True,console_hosts=consoles)
        finally:
            bridge.close()
            if process.state()!=QProcess.NotRunning and not process.waitForFinished(3500):process.kill();process.waitForFinished(2000)
        assert process.state()==QProcess.NotRunning and process.exitCode()==0
        result['clean_exit']=True
        (output/'deck-qt-pipe.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        checks.append('Real AI/media helper: Qt JSON pipe returned offline Pi fixture tokens and cost plus a Windows media snapshot, used no console host, and exited cleanly.')
