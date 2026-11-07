"""Compare the adapted reader with the pinned upstream, including real history."""
import json,os,subprocess,sys,tempfile
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))

def main():
    from run_isolated_test import assert_isolated
    assert_isolated();out=Path(sys.argv[-1]);out.mkdir(parents=True,exist_ok=True)
    sdk=Path('D:/Agant/toolchain/dotnet/dotnet.exe');env=dict(os.environ,DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_CLI_HOME=str(ROOT/'artifacts/dotnet-home'),NUGET_PACKAGES=str(ROOT/'artifacts/nuget'))
    def command(args):
        run=subprocess.run(args,env=env,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW,timeout=100)
        if run.returncode:raise RuntimeError(run.stdout+run.stderr)
        return run.stdout
    programs=[]
    for label in ('original','adapted'):
        target=out/label
        command([str(sdk),'build',str(ROOT/'tests/LogReaderProbe/LogReaderProbe.csproj'),'-c','Release','--source',str(ROOT/'artifacts/nuget-feed'),'-p:UseOriginal='+str(label=='original').lower(),'-o',str(target),'--nologo','-v','quiet'])
        programs.append(target/'LogReaderProbe.dll')
    now=datetime.now(timezone.utc).isoformat();results=[]
    def compare(root,provider,label):
        values=[]
        for program in programs:
            rows=command([str(sdk),str(program),str(root),now,provider]);values.append([json.loads(line) for line in rows.splitlines() if line.startswith('{')])
        equivalent=all(a==b for a,b in zip(values[0],values[1])) and len(values[0])==len(values[1])
        results.append(dict(case=label,equivalent=equivalent,original=values[0],adapted=values[1]))
    with tempfile.TemporaryDirectory(prefix='bigfish-accounting-') as temporary:
        root=Path(temporary);(root/'sessions').mkdir();(root/'projects').mkdir();(root/'pi').mkdir()
        huge='ignored tool output \\"usage\\" '+('abc\\\"中文 '*400000)
        usage=dict(input_tokens=100,cached_input_tokens=30,output_tokens=20)
        count=dict(timestamp=now,type='event_msg',payload=dict(type='token_count',info=dict(total_token_usage=usage,last_token_usage=usage),rate_limits=dict(plan_type='test',primary=dict(used_percent=27,window_minutes=10080))))
        lines=[dict(timestamp=now,type='turn_context',payload=dict(model='fixture',instructions=huge)),dict(timestamp=now,type='response_item',payload=dict(type='message',content=[dict(text=huge)])),count,count]
        def write(path,rows):path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
        write(root/'sessions/test.jsonl',lines);write(root/'sessions/fork.jsonl',[lines[0],count])
        write(root/'projects/test.jsonl',[dict(timestamp=now,type='assistant',message=dict(id='fixture',model='fixture',content=[dict(type='text',text=huge)],usage=dict(input_tokens=100,output_tokens=20,cache_read_input_tokens=30)))])
        write(root/'pi/test.jsonl',[dict(timestamp=now,type='message',id='fixture',message=dict(role='assistant',model='fixture',content=huge,usage=dict(input=100,output=20,cacheRead=30,cost=dict(total=.123))))])
        partial=root/'sessions/partial.jsonl';partial.write_text(json.dumps(dict(count,payload=dict(count['payload'],info=dict(total_token_usage=dict(usage,output_tokens=30),last_token_usage=dict(usage,output_tokens=30)))))[:60],encoding='utf-8')
        compare(root,'Codex,Claude','large values, forks, partial line')
        compare(root/'pi','Pi','large assistant message, reported cost')
    compare(Path.home()/'.codex','Codex','actual local history at fixed cutoff')
    result=dict(passed=all(r['equivalent'] for r in results),cases=results)
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');return 0 if result['passed'] else 1

if __name__=='__main__':sys.exit(main())
