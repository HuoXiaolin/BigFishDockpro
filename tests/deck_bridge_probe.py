"""Exercise the real packaged media pipe; report capabilities, never song/account data."""
import json,queue,subprocess,sys,tempfile,threading,time
from pathlib import Path


def run(executable):
    subprocess.run([str(executable),'--self-test'],check=True,creationflags=subprocess.CREATE_NO_WINDOW)
    with tempfile.TemporaryDirectory(prefix='bigfish-deck-probe-') as root:
        child=subprocess.Popen([str(executable),root],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
        received=queue.Queue()
        def read():
            for line in child.stdout:
                try:received.put(json.loads(line.decode('utf-8-sig')))
                except ValueError:pass
        threading.Thread(target=read,daemon=True).start()
        def send(**data):child.stdin.write((json.dumps(data)+'\n').encode());child.stdin.flush()
        try:
            send(op='configure',ai=False,providers=[],music=True,lyrics=False,equalizer='flow')
            media=[];deadline=time.monotonic()+18
            while time.monotonic()<deadline and len(media)<2:
                try:data=received.get(timeout=.5)
                except queue.Empty:continue
                if data.get('type')=='media':media.append(data)
            assert media,'Real media adapter did not answer'
            assert all(d.get('type')!='ai' for d in media)
            send(op='configure',ai=False,providers=[],music=False,lyrics=False,equalizer='flow')
            send(op='quit');assert child.wait(timeout=8)==0
            return dict(passed=True,media_messages=len(media),players=len(media[-1].get('tracks',[])),has_track=bool(media[-1].get('track')),
                        adapter_error=bool(media[-1].get('status') and media[-1].get('status')!='没有正在播放的媒体'),
                        checks=['real media adapter start/read','disabled AI','media disable','graceful process exit'],
                        limits=['No real playback, seek, shuffle or repeat command sent; AI accounts not queried.'])
        finally:
            if child.poll() is None:child.kill();child.wait(timeout=5)


if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    result=run(root/'artifacts/deck-bridge/BigFishDeckBridge.exe')
    (root/'artifacts/deck-bridge-probe.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
