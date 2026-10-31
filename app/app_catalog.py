"""Application discovery and batch pinning, independent of the GUI."""
import json
import os
import subprocess
import re
from functools import lru_cache
from pathlib import Path

EXTENSIONS = {'.lnk', '.url', '.exe', '.appref-ms', '.bat', '.cmd', '.msc', '.ps1'}

SHELL_TOOLS = [
    ('recycle', '回收站', 'shell:::{645ff040-5081-101b-9f08-00aa002f954e}'),
    ('computer', '此电脑', 'shell:::{20d04fe0-3aea-1069-a2d8-08002b30309d}'),
    ('control', '控制面板', 'shell:::{26ee0668-a00a-44d7-9371-beb064c98683}'),
    ('network','网络','shell:::{f02c1a0d-be21-4350-88b0-7367fc96ef3c}'),
    ('profile','用户文件夹','shell:::{59031a47-3f72-44a7-89c5-5595fe6b30ee}'),
    ('desktop','桌面','shell:Desktop'),
    ('downloads','下载','shell:Downloads'),
    ('documents','文档','shell:Personal'),
    ('pictures','图片','shell:My Pictures'),
    ('music','音乐','shell:My Music'),
    ('videos','视频','shell:My Video'),
]
TOOL_FILES = [('explorer','文件管理','explorer.exe'), ('hyperv','Hyper-V 管理器',r'System32\virtmgmt.msc'),
              ('taskmgr','任务管理器',r'System32\Taskmgr.exe'), ('calculator','计算器',r'System32\calc.exe'),
              ('notepad','记事本',r'System32\notepad.exe'), ('paint','画图',r'System32\mspaint.exe'),
              ('cmd','命令提示符',r'System32\cmd.exe'), ('powershell','PowerShell',r'System32\WindowsPowerShell\v1.0\powershell.exe')]
STORE_TOOLS = {'microsoft.windowscalculator':'calculator', 'microsoft.windowsnotepad':'notepad',
               'microsoft.paint':'paint', 'microsoft.windowsterminal':'terminal',
               'microsoft.windowsstore':'store', 'microsoft.screensketch':'snipping'}


def windows_tool_id(path):
    lower = path.casefold()
    for identity, _, value in SHELL_TOOLS:
        if lower == value.casefold(): return identity
    if lower.startswith('shell:appsfolder\\'):
        package = lower.split('\\',1)[1].split('_',1)[0]
        return STORE_TOOLS.get(package)
    parts = Path(lower).parts
    if 'windowsapps' in parts:
        index = parts.index('windowsapps')+1
        if index < len(parts): return STORE_TOOLS.get(parts[index].split('_',1)[0])
    windir = os.environ.get('WINDIR', r'C:\Windows')
    for identity, _, relative in TOOL_FILES:
        if os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.join(windir,relative)):
            return identity
    return None


def launch_identity(path):
    extra=''
    if isinstance(path,dict):
        extra=str(path.get('arguments') or '').strip();path=path['path']
    try:
        info = os.stat(path)
        stamp = (info.st_mtime_ns, info.st_size)
    except OSError: stamp = None
    return _launch_identity(path, stamp,extra)


@lru_cache(maxsize=1024)
def _launch_identity(path, stamp,extra=''):
    target, arguments, seen = path, extra, set()
    from shortcut_targets import lnk_details
    for _ in range(8):
        key = path_key(target)
        if key in seen: break
        seen.add(key)
        if not target.lower().endswith('.lnk'): break
        details = lnk_details(target)
        if not details: break
        target, args = details
        arguments = (args+' '+arguments).strip()
    apps_folder = 'shell:::{4234d49b-0245-4df3-b780-3893943456e1}\\'
    if target.casefold().startswith(apps_folder): target = 'shell:AppsFolder\\'+target[len(apps_folder):]
    from shortcut_mapping import is_reference
    if is_reference(target) and not target.casefold().startswith('shell:'):return ('url',target,arguments)
    tool = windows_tool_id(target)
    if Path(target).name.casefold() == 'mmc.exe':
        management = arguments.strip('"')
        if windows_tool_id(management) == 'hyperv': return ('windows','hyperv')
    if tool and not arguments: return ('windows', tool)
    if target.lower().endswith('.url'):
        from configparser import ConfigParser, Error
        try:
            parser = ConfigParser(interpolation=None)
            parser.read(target, encoding='utf-8-sig')
            address = parser.get('InternetShortcut','URL',fallback='').strip()
            if address.lower().startswith('file:'):
                from shortcut_targets import shortcut_target
                local = shortcut_target(target)
                if local: return ('target', path_key(local), arguments)
            if address: return ('url', address, arguments)
        except (OSError, UnicodeError, Error): pass
    return ('target', path_key(target), arguments)


def unique_apps(rows):
    """Merge duplicate launch targets for display, retaining their saved paths."""
    result, seen = [], {}
    for row in rows:
        identity = launch_identity(row)
        if identity in seen:
            seen[identity]['_paths'].append(row['path'])
        else:
            item = dict(row, _paths=[row['path']])
            seen[identity] = item
            result.append(item)
    return result


def common_windows_tools():
    rows = [dict(name=name, path=path, column='windows', source='Windows 常用工具') for _,name,path in SHELL_TOOLS]
    for _, name, relative in TOOL_FILES:
        path = os.path.join(os.environ.get('WINDIR',r'C:\Windows'),relative)
        if os.path.isfile(path): rows.append(dict(name=name,path=path,column='windows',source='Windows 常用工具'))
    return rows


def path_key(path):
    if path.lower().startswith(('https://', 'http://')): return path.casefold()
    if path.lower().startswith('shell:'):
        return path.casefold()
    return os.path.normcase(os.path.realpath(os.path.abspath(path))).casefold()


def merge_items(existing, candidates):
    """Keep order and resolved launch metadata; never copy a dragged file."""
    result = [dict(item) for item in existing]
    seen = {launch_identity(i) for i in result if i.get('path') and not i.get('sep')}
    added = duplicates = invalid = 0
    for item in candidates:
        from shortcut_mapping import map_entry,metadata,is_reference
        mapped=map_entry(item)
        if mapped is None:
            invalid+=1;continue
        item=mapped
        path = str(item.get('path', '')).strip()
        store = is_reference(path)
        if not path or (not store and not os.path.exists(path)):
            invalid += 1
            continue
        if launch_identity(item) in seen:
            duplicates += 1
            continue
        seen.add(launch_identity(item))
        result.append({'path': path if store else os.path.abspath(path),
                       'name': item.get('name') or os.path.splitext(os.path.basename(path))[0],
                       'group': item.get('group') or ('Windows 工具' if item.get('column') == 'windows' else infer_group(path, item.get('name', ''))),
                       **metadata(item),**({'icon':item['icon']} if item.get('icon') else {})})
        added += 1
    return result, added, duplicates, invalid


def infer_group(path, name=''):
    if os.path.isdir(path):
        return '文件夹'
    text = (name + ' ' + os.path.basename(path)).casefold()
    for group, words in [('开发', ('studio', 'code', 'python', 'git', 'terminal', 'powershell')),
                         ('办公', ('office', 'word', 'excel', 'wps', 'note', '文档')),
                         ('网络', ('chrome', 'edge', 'firefox', 'browser', '微信', 'qq')),
                         ('影音', ('music', 'video', 'vlc', 'player', '音乐')),
                         ('游戏', ('steam', 'epic', 'game', '游戏'))]:
        if any(word in text for word in words):
            return group
    return '未分类'


def discovery_roots():
    roots = []
    for env, suffix in [('APPDATA', r'Microsoft\Windows\Start Menu\Programs'),
                        ('PROGRAMDATA', r'Microsoft\Windows\Start Menu\Programs'),
                        ('USERPROFILE', 'Desktop'), ('PUBLIC', 'Desktop')]:
        if os.environ.get(env):
            roots.append(os.path.join(os.environ[env], suffix))
    # Honor redirected/OneDrive desktops through Windows Known Folders registry.
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders') as key:
            roots.insert(0, os.path.expandvars(winreg.QueryValueEx(key, 'Desktop')[0]))
    except OSError:
        pass
    return list(dict.fromkeys(roots))


def is_uninstall_entry(row):
    """Filter discovered removal launchers; never remove saved user entries."""
    title = str(row.get('name') or '').strip().casefold()
    if title.startswith(('卸载','反安装','解除安装')) or title.endswith('卸载程序'): return True
    identity = launch_identity(row['path'])
    target = identity[1] if identity[0]=='target' else row['path']
    binary = Path(target).name.casefold()
    # Keep the standalone utility called Uninstall Tool, rather than mistaking it for a removal link.
    if binary not in ('uninstalltool.exe',):
        if re.match(r'^(uninstall(?:er)?|unins[0-9]*)(?:$|[\s_-])',title): return True
    if re.fullmatch(r'(?:uninst(?:all(?:er)?)?|unins[0-9]*|unwise)(?:32|64)?\.exe',binary): return True
    if binary.startswith(('uninstall_','uninstall-')): return True
    args = identity[2] if identity[0]=='target' and len(identity)>2 else ''
    if re.search(r'(?:^|\s)(?:--?|/)uninstall(?:\s|$)',args,re.I): return True
    return binary=='msiexec.exe' and bool(re.search(r'(?:^|\s)/x(?=[{\s]|$)',args,re.I))


def discover_apps(roots=None, include_store=True, cancelled=lambda: False):
    apps = {}
    for root in discovery_roots() if roots is None else roots:
        for directory, dirs, files in os.walk(root, followlinks=False):
            if cancelled():
                return []
            dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(directory, d))]
            for name in files:
                if os.path.splitext(name)[1].lower() not in EXTENSIONS:
                    continue
                path = os.path.join(directory, name)
                title = os.path.splitext(name)[0]
                apps.setdefault(path_key(path), {'name': title, 'path': path,
                                'source': '桌面 / 开始菜单'})
    if include_store and not cancelled():
        for tool in common_windows_tools(): apps.setdefault(path_key(tool['path']), tool)
        # Windows supplies launchable AppUserModelIDs, rather than package IDs.
        command = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; @(Get-StartApps | Where-Object {$_.AppID -like '*!*'}) | ConvertTo-Json -Compress"
        try:
            output = subprocess.check_output(['powershell.exe', '-NoProfile', '-NonInteractive',
                                              '-Command', command], timeout=25,
                                             creationflags=subprocess.CREATE_NO_WINDOW)
            entries = json.loads(output.decode('utf-8-sig'))
            for app in entries if isinstance(entries, list) else [entries]:
                path = 'shell:AppsFolder\\' + app['AppID']
                builtin = app['AppID'].casefold().startswith(('microsoft.', 'windows.', 'microsoftwindows.', 'microsoftcorporationii.'))
                if builtin and not windows_tool_id(path): continue
                apps.setdefault(path_key(path), {'name': app['Name'], 'path': path,
                                'source': 'Windows 应用' if builtin else '商店应用',
                                'column': 'windows' if builtin else 'apps'})
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
            pass
    rows = []
    for app in apps.values():
        identity = launch_identity(app['path'])
        target = identity[1] if identity[0] == 'target' else ''
        system = identity[0] == 'windows' or target.startswith(os.path.normcase(os.environ.get('WINDIR',r'C:\Windows')).casefold()+os.sep)
        parts = Path(target).parts
        if 'windowsapps' in parts:
            index = parts.index('windowsapps')+1
            if index < len(parts) and parts[index].startswith(('microsoft.', 'windows.', 'microsoftwindows.')): system = True
        rows.append(dict(app, column='windows' if system or app.get('column') == 'windows' else 'apps'))
    # Curated Windows tools win over duplicate Start-menu aliases; remaining
    # system components are hidden rather than flooding the ordinary app list.
    tools = {launch_identity(row['path']) for row in common_windows_tools()}
    rows = [row for row in rows if row['column'] != 'windows' or launch_identity(row['path']) in tools or windows_tool_id(row['path'])]
    rows = [row for row in rows if not is_uninstall_entry(row)]
    return sorted(unique_apps(rows), key=lambda a: (a['name'].casefold(), a['path'].casefold()))


def clear_discovery_cache():
    _launch_identity.cache_clear()
