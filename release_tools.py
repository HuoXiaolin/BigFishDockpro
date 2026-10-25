"""Version resources and explicit, non-destructive local delivery export."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
SOURCE_FILES = ['current_ui_tests.py', 'card_metrics.py', 'glass_capture_tests.py', 'glass_capture.py', 'card_sizing_tests.py', 'settings_layout.py', 'card_sizing.py', 'sticky_notes_tests.py', 'sticky_notes.py', 'sticky_notes_store.py', 'external_launch_tests.py', 'desktop_visibility_tests.py', 'native_launch_probe.c', 'external_launch.py', 'desktop_item_visibility.py', 'config_transfer.py', 'config_transfer_tests.py', 'running_apps.py', 'running_apps_tests.py', 'dpi_support.py', 'BigFishDockpro.manifest', 'screen_layout.py', 'screen_layout_tests.py', 'dock.py', 'app_catalog.py', 'batch_import.py', 'settings_dialog.py',
    'feature_config.py', 'runtime_controller.py', 'platform_services.py', 'screen_corners.py',
    'glass_panel.py', 'desktop_panels.py', 'panel_management.py', 'panel_group_tests.py', 'material_tests.py', 'desktop_catalog.py', 'desktop_icons.py', 'desktop_panel_tests.py', 'liquid_glass.py', 'appearance_presets.py',
    'tray_menu.py', 'update_service.py', 'feature_tests.py', 'startup_probe.py',
    'ui_style.py', 'startup_service.py', 'startup_tests.py', 'icon_settings.py', 'shortcut_targets.py', 'interaction_tests.py', 'app_version.py', 'version.json', 'smoke_test.py', 'run_isolated_test.py',
    'BigFishDockpro.spec', 'installer.iss', 'bootstrap.ps1', 'build.ps1', 'release_tools.py',
    'tools_prepare_licenses.py', 'requirements-build.txt', 'dock.ico', 'LICENSE',
    'README.md', '使用说明.md', 'CHANGELOG.md', 'CHANGELOG_HISTORY.md', '.gitignore',
    '1-启动.bat', '2-关闭.bat', '3-修复依赖.bat', '4-调试启动.bat']


def prepare():
    metadata = json.loads((ROOT/'version.json').read_text(encoding='utf-8'))
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).date().isoformat()
    if metadata.get('last_successful_release_date') != today:
        major, minor, patch = map(int, metadata['version'].split('.'))
        patch += 1
        if patch >= 10:
            minor, patch = minor + 1, 0
        metadata['version'] = f'{major}.{minor}.{patch}'
    metadata['last_successful_release_date'] = today
    generated = ROOT/'artifacts/generated'
    generated.mkdir(parents=True, exist_ok=True)
    (generated/'version.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    ver = metadata['version']
    number = tuple(map(int, ver.split('.'))) + (0,)
    text = f'''VSVersionInfo(
 ffi=FixedFileInfo(filevers={number!r}, prodvers={number!r}, mask=0x3f, flags=0,
  OS=0x40004, fileType=1, subtype=0, date=(0,0)),
 kids=[StringFileInfo([StringTable('080404b0', [
  StringStruct('CompanyName', 'HuoXiaolin'),
  StringStruct('FileDescription', '大肥鱼Dock'),
  StringStruct('FileVersion', '{ver}.0'),
  StringStruct('ProductVersion', '{ver}'),
  StringStruct('ProductName', '大肥鱼Dock'),
  StringStruct('InternalName', 'BigFishDockpro'),
  StringStruct('OriginalFilename', 'BigFishDockpro.exe'),
  StringStruct('LegalCopyright', 'Upstream WWQ; modifications HuoXiaolin')
 ])]), VarFileInfo([VarStruct('Translation',[2052,1200])])])
'''
    (generated/'version_info.txt').write_text(text, encoding='utf-8')
    print(ver)


def copy_files(source, target):
    target.mkdir(parents=True, exist_ok=True)
    for path in source.rglob('*'):
        if path.is_file() and not path.is_symlink():
            dest = target/path.relative_to(source)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)


def deliver(source_dir, release_dir, skip_tests=False):
    # Only the named project's leaves are managed. Unknown files and .git survive.
    source, release = Path(source_dir).resolve(), Path(release_dir).resolve()
    if source.name != 'BigFishDockpro' or release.name != 'BigFishDockpro':
        raise ValueError('Delivery targets must be the explicitly named BigFishDockpro directories.')
    if source == ROOT or release == ROOT or source == release:
        raise ValueError('Delivery targets must be separate from the development workspace.')
    installer = ROOT/'release/BigFishDockpro-Setup-x64.exe'
    receipt_path=ROOT/'artifacts/build-validation.json'
    receipt=json.loads(receipt_path.read_text(encoding='utf-8-sig')) if receipt_path.exists() else {}
    if receipt.get('tests_skipped') and not skip_tests:raise RuntimeError('This build skipped tests; explicit --skip-tests is required.')
    if not installer.exists():raise RuntimeError('Build the installer before delivery.')
    if receipt and hashlib.sha256(installer.read_bytes()).hexdigest()!=receipt.get('installer_sha256'):raise RuntimeError('Installer does not match the current build receipt.')
    current_results=receipt.get('validation_results')
    if not skip_tests and current_results is not None:
        if not isinstance(current_results,list) or not current_results:raise RuntimeError('Current build has no validation results.')
        for item in current_results:
            result_path=(ROOT/item['path']).resolve()
            if not result_path.is_relative_to((ROOT/'artifacts').resolve()):raise RuntimeError('Validation path is outside project artifacts.')
            if hashlib.sha256(result_path.read_bytes()).hexdigest()!=item['sha256']:raise RuntimeError('Validation result changed after this build.')
            if not json.loads(result_path.read_text(encoding='utf-8-sig')).get('passed'):raise RuntimeError('Current build validation failed.')
    if not skip_tests and current_results is None and not (ROOT/'artifacts/bundle-test/result.json').exists():
        raise RuntimeError('A verified installer is required before delivery.')
    if not skip_tests and current_results is None and not json.loads((ROOT/'artifacts/bundle-test/result.json').read_text(encoding='utf-8'))['passed']:
        raise RuntimeError('Bundle test did not pass.')
    # Verify the delivered installer before committing the successful release date.
    release.mkdir(parents=True, exist_ok=True)
    target = release/installer.name
    shutil.copy2(installer, target)
    digest = hashlib.sha256(installer.read_bytes()).hexdigest()
    if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
        raise RuntimeError('Delivered installer hash differs.')
    manifest = [digest+'  '+installer.name]
    single = ROOT/'release/BigFishDockpro.exe'
    if single.exists():
        if single.stat().st_mtime < installer.stat().st_mtime:
            raise RuntimeError('Rebuild the single-file artifact alongside the current installer before delivery.')
        result = ROOT/'artifacts/singlefile-test/result.json'
        if not skip_tests and current_results is None and (not result.exists() or not json.loads(result.read_text(encoding='utf-8')).get('passed')):
            raise RuntimeError('Single-file verification is required before delivery.')
        single_digest = hashlib.sha256(single.read_bytes()).hexdigest()
        if receipt and single_digest!=receipt.get('singlefile_sha256'):raise RuntimeError('Single file does not match the current build receipt.')
        shutil.copy2(single, release/single.name)
        if hashlib.sha256((release/single.name).read_bytes()).hexdigest() != single_digest:
            raise RuntimeError('Delivered single-file hash differs.')
        manifest.append(single_digest+'  '+single.name)
    shutil.copy2(ROOT/'artifacts/generated/version.json', ROOT/'version.json')
    source.mkdir(parents=True, exist_ok=True)
    for name in SOURCE_FILES:
        shutil.copy2(ROOT/name, source/name)
    for name in ['licenses', 'docs']:
        copy_files(ROOT/name, source/name)
    source_hashes = []
    for path in sorted(source.rglob('*')):
        relative = path.relative_to(source)
        if '.git' in relative.parts or not path.is_file() or path.name == 'SOURCE_SHA256SUMS.txt':
            continue
        if relative.parts[0] not in SOURCE_FILES + ['licenses', 'docs']:
            continue
        source_hashes.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+relative.as_posix())
    (source/'SOURCE_SHA256SUMS.txt').write_text('\n'.join(source_hashes)+'\n', encoding='utf-8')
    for directory in [ROOT/'release', release]:
        (directory/'SHA256SUMS.txt').write_text('\n'.join(manifest)+'\n', encoding='utf-8')
    report = {'development': str(ROOT), 'source': str(source), 'release': str(release),
              'installer': installer.name, 'sha256': digest, 'source_files': len(source_hashes),
              'version': json.loads((ROOT/'version.json').read_text(encoding='utf-8'))['version'], 'tests_skipped':bool(skip_tests), 'test_scope':receipt.get('test_scope','full' if not skip_tests else 'none')}
    (ROOT/'artifacts/delivery.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'deliver'])
    parser.add_argument('--skip-tests',action='store_true',help='Explicitly deliver a build without running tests.')
    parser.add_argument('--source', default=r'D:\Agant\Github_Source\BigFishDockpro')
    parser.add_argument('--release', default=r'D:\Agant\Github_Releases\BigFishDockpro')
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare()
    else:
        deliver(args.source, args.release, args.skip_tests)
