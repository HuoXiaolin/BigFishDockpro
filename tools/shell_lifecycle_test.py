"""Exercise real native hooks and XAML diagnostics on a private test desktop."""
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback
from itertools import product

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'app'), str(ROOT / 'tools')]


def main(output):
    from run_isolated_test import assert_isolated
    from shell_appearance_model import encode_ini, settings
    output = Path(output)
    checks = []
    try:
        desktop = assert_isolated()
        payload = ROOT / 'artifacts/shell-appearance'
        build = json.loads((payload / 'manifest.json').read_text())['build']
        for kind, mode in product(('start', 'notifications'), ('warm', 'cold', 'retry')):
            case = output / f'{kind}-{mode}'
            case.mkdir(parents=True, exist_ok=True)
            data = settings({f'shell_{kind}_enabled': True, 'dock_material': 'liquid',
                             'theme': 'light', 'transparency': 90}, kind, os.getpid())
            data['probe_lifecycle'] = mode
            index = sum(key.startswith('controlStyles[') and key.endswith('.target') for key in data)
            data[f'controlStyles[{index}].target'] = 'Border#LifecycleSurface'
            data[f'controlStyles[{index}].styles[0]'] = 'Background:=<SolidColorBrush Color="#FF12AB34" />'
            (case / f'{kind}.{build}.ini').write_bytes(encode_ini(data))
            library = 'BigFishStartStyle.dll' if kind == 'start' else 'BigFishNotificationStyle.dll'
            process = subprocess.run([str(ROOT / 'artifacts/shell-build/BigFishShellProbe.exe'),
                                      str(payload / library), str(case)],
                                     creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
            report = case / 'lifecycle-probe.json'
            result = json.loads(report.read_text()) if report.exists() else {}
            if process.returncode or not result.get('passed'):
                raise AssertionError(f'{kind}-{mode}: exit=0x{process.returncode & 0xffffffff:08X}, report={result}')
            checks.append(f'{kind}-{mode}: real MinHook/TAP initialization, visual-tree callback, three refreshes and restore')
        result = {'passed': True, 'scope': 'native-lifecycle-isolated', 'desktop': desktop, 'checks': checks}
    except Exception:
        result = {'passed': False, 'checks': checks, 'error': traceback.format_exc()}
    (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[-1]))
