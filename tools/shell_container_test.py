"""Owned, windowless AppContainer process: package-local DLL/config/status IPC."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'app'), str(ROOT/'tools')]


def main(output, kinds=('notifications', 'start')):
    from run_isolated_test import assert_isolated
    from shell_container import context
    from shell_appearance import shell_hosts
    from shell_appearance_model import encode_ini
    output=Path(output)
    try:
        desktop=assert_isolated()
        targets={}
        for pid, kind in shell_hosts().items():
            if kind not in targets and (container:=context(pid)):
                targets[kind]=container
        payload=ROOT/'artifacts/shell-appearance'
        build=json.loads((payload/'manifest.json').read_text(encoding='utf-8'))['build']
        results={}
        probe=ROOT/'artifacts/shell-build/BigFishContainerProbe.exe'
        for kind, dll, ini, args in (
                ('notifications', 'BigFishNotificationStyle.dll', f'notifications.{build}.ini', []),
                ('start', 'BigFishStartStyle.dll', f'start.{build}.ini', ['start'])):
            if kind not in kinds:continue
            if kind not in targets:raise RuntimeError(f'No {kind} AppContainer available for transport verification')
            target=targets[kind]
            sid=target['event'].split('\\')[-2]
            stage=target['root']/'checks'/('probe-'+uuid.uuid4().hex)
            stage.mkdir(parents=True)
            try:
                for source in (probe, payload/dll):shutil.copyfile(source,stage/source.name)
                (stage/ini).write_bytes(encode_ini({'owner_pid':'0','owner_handle':'0'}))
                process=subprocess.run([str(probe),sid,str(stage),*args],
                    timeout=20,creationflags=subprocess.CREATE_NO_WINDOW,capture_output=True,text=True)
                report=stage/'container-report.json'
                data=json.loads(report.read_text()) if report.is_file() else {}
                if process.returncode or not data.get('passed'):
                    raise RuntimeError(f'{kind} AppContainer child exit={process.returncode}; {data}; {process.stdout} {process.stderr}')
                native=json.loads((stage/'native-status.json').read_text())
                assert native['protocol']==1 and native['state']=='applied' and native['matches']==1
                results[kind]=dict(report=data,native=native)
            finally:
                for name in (probe.name,dll,ini,'container-report.json','native-status.json'):
                    (stage/name).unlink(missing_ok=True)
                stage.rmdir()
        result=dict(passed=True,scope='owned-appcontainer-transport',desktop=desktop,selected_hosts=list(kinds),checks=[
            ', '.join(kinds) + ': bundled DLL loading and package-local configuration reads',
            'Narrow duplicated owner handles and qualified events work, including the build-specific Start/Search event',
            'Shipped native status writers work through single-file write handles',
            'Search AppContainer can read the anonymous geometry slot and cannot write it'], hosts=results, **results[kinds[0]])
    except Exception:
        result=dict(passed=False,error=traceback.format_exc())
    (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if result['passed'] else 1


if __name__=='__main__':sys.exit(main(sys.argv[-1]))
