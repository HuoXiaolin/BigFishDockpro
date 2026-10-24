"""Desktop reference classification. No moving, deleting or hiding source files."""
import os
import threading
import uuid
import re
from pathlib import Path
from PyQt5.QtCore import QObject, pyqtSignal
from app_catalog import path_key, EXTENSIONS

CATEGORIES = [('apps', '应用'), ('folders', '文件夹'), ('documents', '文档'),
              ('images', '图片'), ('media', '影音'), ('archives', '压缩包'), ('other', '其他')]
DOCUMENTS = {'.pdf', '.txt', '.md', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
             '.csv', '.rtf', '.odt', '.ods', '.json', '.xml', '.yaml', '.yml'}
IMAGES = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.ico', '.svg', '.tif', '.tiff', '.heic'}
MEDIA = {'.mp3', '.wav', '.flac', '.m4a', '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.webm'}
ARCHIVES = {'.zip', '.7z', '.rar', '.tar', '.gz', '.bz2', '.xz', '.iso'}


def category(path, _seen=None):
    if os.path.isdir(path): return 'folders'
    suffix = Path(path).suffix.casefold()
    if suffix in ('.lnk', '.url'):
        seen = set() if _seen is None else _seen
        key = os.path.abspath(path).casefold()
        if key in seen or len(seen) >= 8: return 'apps'
        seen.add(key)
        from shortcut_targets import shortcut_target
        target = shortcut_target(path)
        if target: return 'apps' if target.lower().startswith('shell:') else category(target, seen)
    if suffix in EXTENSIONS: return 'apps'
    if suffix in DOCUMENTS: return 'documents'
    if suffix in IMAGES: return 'images'
    if suffix in MEDIA: return 'media'
    if suffix in ARCHIVES: return 'archives'
    return 'other'


def desktop_roots():
    roots = []
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders') as key:
            roots.append(os.path.expandvars(winreg.QueryValueEx(key, 'Desktop')[0]))
    except OSError:
        if os.environ.get('USERPROFILE'):
            roots.append(os.path.join(os.environ['USERPROFILE'], 'Desktop'))
    if os.environ.get('PUBLIC'):
        roots.append(os.path.join(os.environ['PUBLIC'], 'Desktop'))
    return list(dict.fromkeys(roots))


def scan_desktop(roots, cancelled=lambda: False, included_hidden=()):
    included_hidden=set(included_hidden)
    rows, errors, seen = [], [], set()
    for root in roots:
        if cancelled(): break
        try:
            with os.scandir(root) as entries:
                for entry in entries:
                    if cancelled(): return [], errors
                    if entry.name.casefold() in ('desktop.ini', 'thumbs.db') or entry.name.startswith('.'):
                        continue
                    try:
                        # Respect hidden/system files; don't recurse into folders or junctions.
                        info = entry.stat(follow_symlinks=False)
                        attrs=getattr(info,'st_file_attributes',0)
                        if attrs&4 or (attrs&2 and path_key(entry.path) not in included_hidden):continue
                        key = path_key(entry.path)
                        if key not in seen:
                            seen.add(key)
                            rows.append({'path': os.path.abspath(entry.path), 'name': entry.name,
                                         'panel': category(entry.path), 'source': 'desktop'})
                    except OSError as error:
                        errors.append(str(error))
        except OSError as error:
            errors.append(str(error))
    return sorted(rows, key=lambda row: row['name'].casefold()), errors


def effective_suffix(path):
    seen = set()
    while Path(path).suffix.casefold() in ('.lnk','.url') and path_key(path) not in seen and len(seen)<8:
        seen.add(path_key(path))
        from shortcut_targets import shortcut_target
        target = shortcut_target(path)
        if not target or target.lower().startswith('shell:'): break
        path = target
    return '' if os.path.isdir(path) else Path(path).suffix.casefold()


def parse_extensions(value):
    tokens = re.split(r'[\s,;，；]+', str(value or '').strip().casefold())
    result = []
    for token in tokens:
        if not token: continue
        token = token.removeprefix('*').lstrip('.')
        if not re.fullmatch(r'[a-z0-9][a-z0-9_+-]{0,31}', token):
            raise ValueError('格式请填写扩展名，例如 .pdf .docx .png，用空格或逗号分隔。')
        if '.'+token not in result: result.append('.'+token)
        if len(result)>64: raise ValueError('每个面板最多设置 64 种格式。')
    return result


def reconcile(existing, scanned, excluded):
    blocked = set(excluded)
    incoming = {path_key(row['path']): row for row in scanned if path_key(row['path']) not in blocked}
    result, seen, paths = [], set(), set()
    for row in existing:
        key = path_key(row['path'])
        if key in blocked or (row.get('source')=='desktop' and key not in incoming): continue
        updated = dict(row)
        if key in incoming:
            updated['name'] = incoming[key]['name']
            if row.get('source')=='desktop' and row.get('panel') in {identity for identity,_ in CATEGORIES}:
                updated['panel'] = incoming[key]['panel']
        pair = (key,updated['panel'])
        if pair not in seen:
            result.append(updated); seen.add(pair); paths.add(key)
    for key,row in incoming.items():
        if key not in paths: result.append(dict(row))
    return result


def normalize_desktop(cfg):
    panels, seen = [], set()
    for raw in cfg.get('desktop_panels', []) if isinstance(cfg.get('desktop_panels'), list) else []:
        if not isinstance(raw, dict): continue
        identity = str(raw.get('id') or uuid.uuid4().hex)[:80]
        if identity in seen: continue
        seen.add(identity)
        panel = {'id': identity, 'name': str(raw.get('name') or '收纳面板')[:40]}
        if type(raw.get('font_size')) is int and 8<=raw['font_size']<=48:panel['font_size']=raw['font_size']
        if type(raw.get('font_scale')) in (int,float) and .125<=raw['font_scale']<=8:panel['font_scale']=float(raw['font_scale'])
        geo = raw.get('geometry')
        if isinstance(geo, list) and len(geo) == 4 and all(type(n) is int for n in geo):
            panel['geometry'] = [geo[0], geo[1], max(260, min(2400, geo[2])), max(156, min(1800, geo[3]))]
        for key, low, high in [('opacity', 0, 100), ('blur', 2, 30), ('highlight', 0, 100), ('capsule_ratio', 30, 100)]:
            if type(raw.get(key)) is int: panel[key] = max(low, min(high, raw[key]))
        for key in ('locked', 'auto_hide', 'collapsed', 'compact', 'enabled', 'merged'):
            if isinstance(raw.get(key), bool): panel[key] = raw[key]
        if raw.get('collapse_style') in ('bar', 'capsule'): panel['collapse_style'] = raw['collapse_style']
        if raw.get('view') in ('small','large','list'): panel['view'] = raw['view']
        if raw.get('sort') in ('name_asc', 'name_desc', 'modified_desc', 'modified_asc'): panel['sort'] = raw['sort']
        if raw.get('material') in ('liquid', 'gloss', 'acrylic', 'mica', 'clear', 'solid'): panel['material'] = raw['material']
        if raw.get('theme') in ('auto', 'light', 'dark'): panel['theme'] = raw['theme']
        if raw.get('theme') == 'follow': panel['theme'] = 'auto'
        if raw.get('theme') == 'gloss': panel.update(theme='light', material='gloss')
        if raw.get('color') == '' or re.fullmatch(r'#[0-9a-fA-F]{6}', str(raw.get('color') or '')):
            panel['color'] = str(raw.get('color') or '').lower()
        if isinstance(raw.get('extensions'),list):
            try: panel['extensions'] = parse_extensions(' '.join(str(value) for value in raw['extensions']))
            except ValueError: panel['extensions'] = []
        for key in ('excluded', 'pinned_paths'):
            if isinstance(raw.get(key),list): panel[key] = list(dict.fromkeys(str(value) for value in raw[key]))
        panels.append(panel)
    entries, seen = [], set()
    for row in cfg.get('desktop_entries', []) if isinstance(cfg.get('desktop_entries'), list) else []:
        if not isinstance(row, dict) or not isinstance(row.get('path'), str) or not row['path'].strip(): continue
        key = (path_key(row['path']), str(row.get('panel') or 'other'))
        if key in seen: continue
        seen.add(key)
        entries.append({'path': row['path'], 'name': str(row.get('name') or Path(row['path']).name),
                        'panel': str(row.get('panel') or 'other')[:80],
                        'source': 'desktop' if row.get('source') == 'desktop' else 'manual',
                        **({'pinned': row['pinned']} if isinstance(row.get('pinned'), bool) else {})})
    excluded = cfg.get('desktop_excluded')
    return {'desktop_panels': panels, 'desktop_entries': entries,
            'desktop_excluded': list(dict.fromkeys(str(key) for key in excluded)) if isinstance(excluded, list) else []}


class DesktopScan(QObject):
    ready = pyqtSignal(object, object)

    def __init__(self, roots, included_hidden=()):
        super().__init__()
        self.roots = list(roots)
        self.included_hidden=tuple(included_hidden)
        self.cancelled = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self): self.thread.start()

    def run(self):
        rows, errors = scan_desktop(self.roots, self.cancelled.is_set, self.included_hidden)
        if not self.cancelled.is_set(): self.ready.emit(rows, errors)

    def close(self):
        self.cancelled.set()
        if self.thread.is_alive(): self.thread.join(.3)
