"""Prepare local cursor archives and verify cursor data in every Dock build."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / 'artifacts' / 'local-cursor-styles'
sys.path.insert(0, str(ROOT / 'app'))
from cursor_styles import ARCHIVES, BUILTINS, manifest_files, read_pack
from cursor_windows import CursorSystem


def prepare():
    source = ROOT / '鼠标样式'
    if not source.is_dir():
        entries = json.loads((PAYLOAD / 'index.json').read_text(encoding='utf-8'))
        for name, filename in entries:
            archive = PAYLOAD / filename
            if archive.parent != PAYLOAD or ':' in filename or read_pack(archive)[0] != name:
                raise ValueError(f'Invalid local cursor archive: {name}')
        print(f'Local cursor schemes: {len(entries)} verified archives')
        return
    builtins = {name.casefold(): ARCHIVES / filename for name, filename in BUILTINS}
    PAYLOAD.mkdir(parents=True, exist_ok=True)
    entries = []
    seen = set()
    with TemporaryDirectory(dir=PAYLOAD, prefix='prepare-') as directory:
        stage = Path(directory)
        folders = [source, *sorted(path for path in source.iterdir() if path.is_dir())]
        for folder in folders:
            for manifest in manifest_files(folder):
                name, mapping, files = read_pack(manifest)
                key = name.casefold()
                if key in seen:
                    raise ValueError(f'Duplicate cursor scheme: {name}')
                seen.add(key)
                if key in builtins and read_pack(builtins[key]) == (name, mapping, files):
                    continue
                CursorSystem.check_files(manifest.parent / filename for filename in mapping.values())
                archive_name = hashlib.sha256(name.encode('utf-8')).hexdigest()[:16] + '.tar.xz'
                archive = stage / archive_name
                with tarfile.open(archive, 'w:xz', preset=6) as stream:
                    for filename, data in sorted(files.items()):
                        member = tarfile.TarInfo(filename)
                        member.size = len(data)
                        stream.addfile(member, io.BytesIO(data))
                if read_pack(archive) != (name, mapping, files):
                    raise ValueError(f'Cursor archive does not match its source: {name}')
                entries.append((name, archive_name))
        if not entries:
            raise ValueError('No local cursor schemes found.')
        (stage / 'index.json').write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding='utf-8')
        for _, name in entries:
            (stage / name).replace(PAYLOAD / name)
        (stage / 'index.json').replace(PAYLOAD / 'index.json')
    print(f'Local cursor schemes: {len(entries)}, {sum((PAYLOAD / name).stat().st_size for _, name in entries):,} compressed bytes')


def verify(single_file):
    prefix = Path('assets') / 'cursor-styles'
    files = {prefix / archive: ARCHIVES / archive for _, archive in BUILTINS}
    local_enabled = os.environ.get('FISHDOCK_LOCAL_CURSOR_STYLES') == '1'
    entries = []
    if local_enabled:
        entries = json.loads((PAYLOAD / 'index.json').read_text(encoding='utf-8'))
        local_names = ['index.json', *(name for _, name in entries)]
        files.update({prefix / 'local' / name: PAYLOAD / name for name in local_names})
    for scheme, archive in [*BUILTINS, *entries]:
        source = ARCHIVES / archive if (scheme, archive) in BUILTINS else PAYLOAD / archive
        if read_pack(source)[0] != scheme:
            raise ValueError(f'Cursor manifest name differs from catalog: {scheme}')
    directory = ROOT / 'dist' / 'BigFishDockpro' / '_internal'
    names = {'directory bundle'}
    archives = []
    if single_file:
        from PyInstaller.archive.readers import CArchiveReader
        packages = ['BigFishDockpro.exe']
        if os.environ.get('FISHDOCK_BUNDLE_DOTNET') == '1':
            from portable_dotnet import BASENAME
            packages.append(BASENAME)
        for basename in packages:
            reader = CArchiveReader(str(ROOT / 'release' / basename))
            archives.append((basename, reader, {Path(name): name for name in reader.toc}))
            names.add(basename)
    expected_paths = set(files)
    directory_paths = {path.relative_to(directory) for path in (directory / prefix).rglob('*') if path.is_file()}
    if directory_paths != expected_paths:
        raise ValueError('Directory bundle cursor catalog does not match the build configuration.')
    for basename, _, paths in archives:
        if {key for key in paths if key.is_relative_to(prefix)} != expected_paths:
            raise ValueError(f'{basename} cursor catalog does not match the build configuration.')
    for key, source in files.items():
        expected = source.read_bytes()
        if (directory / key).read_bytes() != expected:
            raise ValueError(f'Directory bundle cursor data differs: {key}')
        for basename, reader, paths in archives:
            if key not in paths or reader.extract(paths[key]) != expected:
                raise ValueError(f'{basename} cursor data differs: {key}')
    result = {'passed': True, 'bundles': sorted(names),
              'schemes': [name for name, _ in [*BUILTINS, *entries]],
              'compressed_bytes': sum(path.stat().st_size for path in files.values()),
              'local_files': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in files.values() if path.parent == PAYLOAD}}
    proof = PAYLOAD / 'result.json' if local_enabled else ROOT / 'artifacts/cursor-builtins-verification.json'
    proof.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"Verified cursor payload in {len(names)} bundles")


if __name__ == '__main__':
    if sys.argv[1:] == ['prepare']:
        prepare()
    elif sys.argv[1:] in (['verify'], ['verify', '--single-file']):
        verify('--single-file' in sys.argv[1:])
    else:
        raise SystemExit('Usage: pack_cursor_styles.py prepare | verify [--single-file]')
