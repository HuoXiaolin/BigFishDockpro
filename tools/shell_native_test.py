"""Validate the shipped native engines on a private desktop, with synthetic XAML."""
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'app'), str(ROOT / 'tools')]


def main(output):
    from run_isolated_test import assert_isolated
    from shell_appearance_model import settings, encode_ini, normalize
    output = Path(output).resolve()
    checks = []
    try:
        desktop = assert_isolated()
        executable = ROOT / 'artifacts/shell-build/BigFishShellProbe.exe'
        cases = [(material, 'light', 72, 'auto') for material in ('crystal', 'acrylic', 'solid', 'clear', 'flowing', 'paper_glass')]
        cases += [(material, 'dark', 0, 'auto') for material in ('crystal', 'acrylic', 'clear')]
        cases += [('liquid', 'light', opacity, 'auto') for opacity in (0, 25, 50, 100)]
        cases += [('liquid', 'light', 25, 'white'), ('liquid', 'dark', 25, 'black')]
        for kind, filename, inspected in (
                ('start', 'BigFishStartStyle.dll', 'rounded backing, shadow cleanup, two visible native columns and restoration'),
                ('notifications', 'BigFishNotificationStyle.dll', 'surface and inherited quick-settings theme with native restoration')):
            for material, theme, opacity, text_mode in cases:
                case = output / f'{kind}-{material}-{theme}-{opacity}-{text_mode}'
                case.mkdir(parents=True, exist_ok=True)
                cfg = normalize({f'shell_{kind}_enabled': True,
                                 f'shell_{kind}_text_mode': text_mode,
                                 'dock_material': material, 'theme': theme, 'transparency': 100 - opacity})
                if material == 'liquid':
                    cfg.update({f'shell_{kind}_source': 'custom', f'shell_{kind}_material': material,
                                f'shell_{kind}_theme': theme, f'shell_{kind}_opacity': opacity})
                expected = 0 if material == 'clear' else opacity
                data = settings(cfg, kind, os.getpid())
                data.update(probe_tint_percent=str(expected), probe_tint_alpha=str(round(expected * 255 / 100)))
                (case / (kind + '.ini')).write_bytes(encode_ini(data))
                result = subprocess.run([str(executable), str(ROOT / 'artifacts/shell-appearance' / filename), str(case)],
                                        creationflags=subprocess.CREATE_NO_WINDOW, timeout=12)
                report = case / (kind + '-probe.json')
                data = json.loads(report.read_text()) if report.exists() else {}
                if result.returncode or not data.get('passed'):
                    raise AssertionError(f'{case.name}: exit={result.returncode}, result={data}')
                checks.append(case.name + ': verified tint and ' + inspected)
        result = {'passed': True, 'scope': 'native-xaml-isolated', 'desktop': desktop, 'checks': checks,
                  'limits': ['Synthetic native XAML; no injection into the user shell or live Windows start/notification interaction.']}
    except Exception:
        result = {'passed': False, 'checks': checks, 'error': traceback.format_exc()}
    (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[-1]))
