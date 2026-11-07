"""Read-only real-account bridge measurement. No playback or working-set trimming."""
import json,queue,statistics,subprocess,sys,tempfile,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'tools')]
from resource_memory_runner import sample

def main():
    from run_isolated_test import assert_isolated
    assert_isolated();out=Path(sys.argv[-1]);out.mkdir(parents=True,exist_ok=True)
    result={'scope':'Private desktop, actual local Codex history and read-only quota/pricing calls, media discovery, no playback controls, no memory trimming','stages':[]}
    with tempfile.TemporaryDirectory(prefix='bigfish-memory-history-') as data:
        child=subprocess.Popen([str(ROOT/'artifacts/deck-bridge/BigFishDeckBridge.exe'),data],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
        messages=queue.Queue()
        def read():
            for line in child.stdout:
                try:
                    item=json.loads(line.decode('utf-8-sig'))
                    if item.get('type')=='ai':
                        rows=item.get('providers',[])
                        messages.put({'available':all(r.get('usageAvailable') for r in rows),'complete':all(r.get('usageComplete') for r in rows),'groups':sum(len(r.get('days',[])) for r in rows),'records':sum(d['summary']['records'] for r in rows for d in r.get('days',[]))})
                except ValueError:pass
        threading.Thread(target=read,daemon=True).start()
        def send(**value):child.stdin.write((json.dumps(value)+'\n').encode());child.stdin.flush()
        try:
            send(op='configure',ai=True,providers=['Codex'],music=True,lyrics=False,equalizer='flow',presentation=False)
            for name,command in [('recent',None),('all',dict(op='history',range='all')),('repeat',dict(op='refresh')),('visible_wave',dict(op='refresh'))]:
                if name=='visible_wave':send(op='configure',ai=True,providers=['Codex'],music=True,lyrics=False,equalizer='spectrum',presentation=True)
                if command:send(**command)
                samples=[];snapshot=None;until=time.monotonic()+80
                while time.monotonic()<until and child.poll() is None:
                    samples.append(sample(child.pid))
                    try:snapshot=messages.get_nowait();until=min(until,time.monotonic()+5)
                    except queue.Empty:pass
                    time.sleep(.1)
                if not snapshot:raise RuntimeError('No AI response during '+name)
                result['stages'].append(dict(name=name,peak={k:max(s[k] for s in samples) for k in samples[0]},settled={k:statistics.median(s[k] for s in samples[-20:]) for k in samples[0]},snapshot=snapshot))
                (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
                assert snapshot['available'] and snapshot['complete'],'Usage incomplete in '+name
                assert max(s['private_working_set_mib'] for s in samples)<50 and max(s['peak_private_commit_mib'] for s in samples)<=50,'Exceeded process memory budget in '+name
            send(op='quit');assert child.wait(timeout=6)==0;result['passed']=True
        except Exception as exc:result.update(passed=False,error=str(exc))
        finally:
            if child.poll() is None:child.kill();child.wait(timeout=5)
    (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');return 0 if result.get('passed') else 1

if __name__=='__main__':sys.exit(main())
