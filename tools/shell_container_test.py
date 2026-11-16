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


def main(output):
    from run_isolated_test import assert_isolated
    from shell_container import context
    from shell_appearance import shell_hosts
    from shell_appearance_model import encode_ini
    output=Path(output);stage=None
    try:
        desktop=assert_isolated()
        target=next((c for pid in shell_hosts() if (c:=context(pid))),None)
        if not target:raise RuntimeError('No notification AppContainer available for transport verification')
        sid=target['event'].split('\\')[-2]
        stage=target['root']/'checks'/('probe-'+uuid.uuid4().hex)
        stage.mkdir(parents=True)
        for source in (ROOT/'artifacts/shell-build/BigFishContainerProbe.exe',ROOT/'artifacts/shell-appearance/BigFishNotificationStyle.dll'):
            shutil.copyfile(source,stage/source.name)
        (stage/'notifications.ini').write_bytes(encode_ini({'owner_pid':'0','owner_handle':'0'}))
        process=subprocess.run([str(ROOT/'artifacts/shell-build/BigFishContainerProbe.exe'),sid,str(stage)],
            timeout=20,creationflags=subprocess.CREATE_NO_WINDOW,capture_output=True,text=True)
        report=stage/'container-report.json'
        data=json.loads(report.read_text()) if report.is_file() else {}
        if process.returncode or not data.get('passed'):
            raise RuntimeError(f'AppContainer child exit={process.returncode}; {data}; {process.stdout} {process.stderr}')
        native=json.loads((stage/'native-status.json').read_text())
        assert native['protocol']==1 and native['state']=='applied' and native['matches']==1
        result=dict(passed=True,scope='owned-appcontainer-transport',desktop=desktop,checks=[
            'AppContainer loads bundled notification DLL and reads package-local configuration',
            'Narrow duplicated owner handle and qualified event work across the sandbox boundary',
            'Shipped native status writer works through the single-file write handle; no shell injection or application-directory ACL changes'],report=data,native=native)
    except Exception:
        result=dict(passed=False,error=traceback.format_exc())
    finally:
        if stage is not None:
            # Delete only the three exact test files and our generated report.
            for name in ('BigFishContainerProbe.exe','BigFishNotificationStyle.dll','notifications.ini','container-report.json','native-status.json'):
                (stage/name).unlink(missing_ok=True)
            stage.rmdir()
    (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if result['passed'] else 1


if __name__=='__main__':sys.exit(main(sys.argv[-1]))
