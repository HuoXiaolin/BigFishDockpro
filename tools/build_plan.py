"""Choose release checks from changes since the last verified local delivery."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL_FILES = {'tools/prepare_shell_appearance.py', 'tools/shell_native_test.py',
               'tools/shell_lifecycle_test.py', 'tools/shell_controller_test.py'}
PIPELINE_FILES = {'build.ps1', 'tools/build.ps1', 'tools/build_plan.py',
                  'tests/test_build_plan.py'}
DOC_FILES = {'README.md', 'CHANGELOG.md', 'CHANGELOG_HISTORY.md', '使用说明.md'}


def classify(changed, baseline_verified):
    if not baseline_verified:
        return 'runtime'
    relevant = [name for name in changed if name not in PIPELINE_FILES | DOC_FILES
                and not name.startswith('docs/')]
    shell = lambda name: name in SHELL_FILES or name.startswith(('app/shell_appearance', 'tools/ShellAppearance/'))
    return 'shell' if relevant and all(shell(name) for name in relevant) else 'runtime'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def make_plan(source):
    from release_tools import SOURCE_FILES
    source = source.resolve()
    verified, baseline, error = False, {}, ''
    try:
        delivery = json.loads((ROOT / 'artifacts/delivery.json').read_text(encoding='utf-8-sig'))
        if Path(delivery['source']).resolve() != source or delivery['tests_skipped']:
            raise ValueError('No verified delivery for this source export')
        for line in (source / 'SOURCE_SHA256SUMS.txt').read_text(encoding='utf-8-sig').splitlines():
            sha, name = line.split('  ', 1)
            path = (source / name).resolve()
            if not path.is_relative_to(source) or digest(path) != sha:
                raise ValueError('Source baseline changed: ' + name)
            baseline[name] = sha
        if not baseline or len(baseline) != delivery['source_files']:
            raise ValueError('Incomplete source baseline')
        verified = True
    except (OSError, ValueError, KeyError) as exc:
        error = str(exc)
    current = {name: digest(ROOT / name) for name in SOURCE_FILES if (ROOT / name).is_file()}
    changed = sorted(name for name in current.keys() | baseline.keys() if current.get(name) != baseline.get(name))
    profile = classify(changed, verified)
    return {'profile': profile, 'baseline_verified': verified, 'baseline_error': error,
            'changed_files': changed,
            'reason': ('Only Shell appearance changed; native layout, lifecycle and both package startups.'
                       if profile == 'shell' else 'Run the complete packaged UI runtime checks.')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    plan = make_plan(args.source)
    args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
    print(plan['profile'])
