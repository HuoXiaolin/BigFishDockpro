"""Load original cursor files and keep applied schemes outside the executable."""
import csv
import hashlib
import json
import locale
import lzma
import re
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from tempfile import TemporaryDirectory

from PyQt5.QtCore import QObject, pyqtSignal

from cursor_windows import KEY, ROLES, CursorSystem, native_default


ARCHIVES = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'assets' / 'cursor-styles'
BUILTINS = (
    ('Bibata-Modern-Amber-Regular Cursors', 'bibata-amber-2.0.6.tar.xz'),
    ('Bibata-Modern-Ice-Regular Cursors', 'bibata-ice-2.0.6.tar.xz'),
    ('【玻璃通透】Spirit', 'bibata-spirit.tar.xz'),
    ('【玻璃通透】Tinted Glass', 'bibata-tinted-glass.tar.xz'),
    ('【动态个性】Future', 'future.tar.xz'),
    ('【圆润几何】Layan White', 'layan-white.tar.xz'),
    ('【圆润几何】Phinger Light', 'phinger-light.tar.xz'),
)
TITLES = {
    BUILTINS[0][0]: 'Bibata 琥珀',
    BUILTINS[1][0]: 'Bibata 冰白',
    BUILTINS[2][0]: 'Spirit 玻璃',
    BUILTINS[3][0]: 'Tinted Glass',
    BUILTINS[4][0]: 'Future 动态',
    BUILTINS[5][0]: 'Layan 白色',
    BUILTINS[6][0]: 'Phinger 浅色',
    'W11 Cursor Light Free v2.2 by Jepri Creations': 'Windows 11 浅色',
    'GrokBot-Soft-Pointer': '柔光动态',
    '【动态个性】酷狗老皮': '酷狗老皮',
    '【动态个性】路飞': '路飞',
}
CURSOR_EXTENSIONS = {'.cur', '.ani'}
NOTICE_FILES = {'license.txt', '作者与来源.txt'}
PACK_LIMIT = 64 * 1024 * 1024
INF_LIMIT = 128 * 1024
PACK_ERRORS = (OSError, ValueError, csv.Error, lzma.LZMAError, tarfile.TarError)


@dataclass(frozen=True)
class CursorStyle:
    name: str
    source: Path

    @property
    def title(self):
        return TITLES.get(self.name, self.name)


def parse_inf(data, fallback):
    if len(data) > INF_LIMIT:
        raise ValueError('鼠标方案的 INF 文件过大。')
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        contents = data.decode('utf-16')
    else:
        try:
            contents = data.decode('utf-8-sig')
        except UnicodeDecodeError:
            contents = data.decode(locale.getpreferredencoding(False), errors='replace')
    sections = {}
    section = None
    for line in contents.splitlines():
        line = re.split(r';(?=(?:[^"]*"[^"]*")*[^"]*$)', line, maxsplit=1)[0].strip()
        if line.startswith('[') and line.endswith(']'):
            section = sections.setdefault(line[1:-1].strip().casefold(), [])
        elif line and section is not None:
            section.append(line)
    strings = {}
    for line in sections.get('strings', ()):
        key, separator, value = line.partition('=')
        if separator:
            strings[key.strip().casefold()] = value.strip().strip('"')

    def expand(text):
        return re.sub(r'%([^%]+)%', lambda match: strings.get(match[1].casefold(), match[0]), text)

    roles = {role.casefold(): role for role in ROLES}
    name = strings.get('scheme_name', fallback)
    files = {}
    for section_name, lines in sections.items():
        if section_name in ('strings', 'version', 'destinationdirs'):
            continue
        for row in csv.reader(lines, skipinitialspace=True):
            if len(row) != 5 or row[0].strip().casefold() != 'hkcu' or row[1].strip().casefold() != KEY.casefold():
                continue
            value_name = row[2].strip().casefold()
            value = expand(row[4].strip())
            if value_name in roles:
                # The INF path is the original setup destination. Import the named
                # file from the selected folder, independent of that destination.
                file = PureWindowsPath(value).name
                if Path(file).suffix.casefold() in CURSOR_EXTENSIONS:
                    files[roles[value_name]] = file
            elif not value_name and value and '%' not in value:
                name = value
    if 'Arrow' not in files:
        raise ValueError('方案缺少普通指针的文件映射。')
    return (name.strip() or fallback)[:128], files


def is_manifest(path):
    return path.suffix.casefold() == '.inf' or path.name.casefold() == 'pack.ini'


def manifest_files(folder):
    return sorted(path for path in folder.glob('*') if is_manifest(path) and path.is_file())


def parse_manifest(path, data, fallback):
    if path.suffix.casefold() == '.inf':
        return parse_inf(data, fallback)
    if len(data) > INF_LIMIT:
        raise ValueError('鼠标方案的 pack.ini 文件过大。')
    settings = {}
    for line in data.decode('utf-8-sig').splitlines():
        key, separator, value = line.partition('=')
        if separator:
            settings[key.strip().casefold()] = value.strip()
    files = {role: settings[role.casefold()] for role in ROLES if settings.get(role.casefold())}
    if 'Arrow' not in files:
        raise ValueError('方案缺少普通指针的文件映射。')
    return (settings.get('name') or fallback)[:128], files


def bundled_styles(folder):
    sources = [(name, folder / file) for name, file in BUILTINS]
    local = folder / 'local'
    try:
        entries = json.loads((local / 'index.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        entries = []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, list) or len(entry) != 2:
            continue
        name, file = entry
        if (isinstance(name, str) and isinstance(file, str) and file.endswith('.tar.xz') and
                PureWindowsPath(file).name == file and ':' not in file):
            sources.append((name, local / file))
    return [CursorStyle(name, path) for name, path in sources if path.is_file()]


def read_pack(source):
    """Read regular cursor files and the manifest. No installer directives are run."""
    files = {}
    if source.suffix == '.xz':
        with tarfile.open(source, mode='r|xz') as archive:
            size = 0
            for member in archive:
                path = PureWindowsPath(member.name)
                if (not member.isfile() or path.name != member.name or ':' in member.name or
                        not (is_manifest(path) or path.suffix.casefold() in CURSOR_EXTENSIONS or
                             path.name.casefold() in NOTICE_FILES)):
                    raise ValueError('内置鼠标方案包含无效文件。')
                size += member.size
                if size > PACK_LIMIT:
                    raise ValueError('鼠标样式文件过大。')
                with archive.extractfile(member) as stream:
                    files[member.name] = stream.read()
    else:
        folder = source.parent.resolve()
        candidates = [source, *(file for file in folder.iterdir() if file.is_file() and
                                (file.suffix.casefold() in CURSOR_EXTENSIONS or
                                 file.name.casefold() in NOTICE_FILES))]
        size = 0
        for path in candidates:
            if not path.resolve().is_relative_to(folder):
                raise ValueError('方案文件须位于同一文件夹。')
            size += path.stat().st_size
            if size > PACK_LIMIT:
                raise ValueError('鼠标样式文件过大。')
            files[path.name] = path.read_bytes()
    manifests = [path for path in files if is_manifest(Path(path))]
    if len(manifests) != 1:
        raise ValueError('鼠标方案需要一个 INF 或 pack.ini 文件。')
    manifest = manifests[0]
    name, mapping = parse_manifest(Path(manifest), files[manifest], source.parent.name)
    case_map = {file.casefold(): file for file in files}
    for role, file in mapping.items():
        actual = case_map.get(file.casefold())
        if actual is None or Path(actual).suffix.casefold() not in CURSOR_EXTENSIONS:
            raise ValueError(f'找不到指针文件 {file}。')
        data = files[actual]
        valid = (data.startswith(b'RIFF') and data[8:12] == b'ACON' if file.lower().endswith('.ani')
                 else data[:4] == b'\0\0\x02\0' and len(data) >= 22)
        if not valid:
            raise ValueError(f'无法读取指针文件 {file}。')
        mapping[role] = actual
    return name, mapping, files


class CursorStyles(QObject):
    changed = pyqtSignal()

    def __init__(self, config, system, archives=ARCHIVES, local=None):
        super().__init__()
        self.library = (Path(config) / 'cursor-styles').absolute()
        self.system = system
        self.archives = archives
        self.local = Path(local) if local is not None else (
            Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]
        ) / '鼠标样式'

    def styles(self):
        styles = {style.name.casefold(): style for style in bundled_styles(self.archives)}
        folders = sorted((self.library / 'imported').glob('*'))
        folders += [self.local, *sorted(self.local.glob('*'))]
        for folder in folders:
            if not folder.is_dir():
                continue
            for source in manifest_files(folder):
                try:
                    with source.open('rb') as stream:
                        name, _ = parse_manifest(source, stream.read(INF_LIMIT + 1), folder.name)
                except PACK_ERRORS:
                    continue
                styles.setdefault(name.casefold(), CursorStyle(name, source))
        return list(styles.values())

    def current(self, styles):
        values = self.system.read()
        name = values.get('', ('',))[0]
        arrow = values.get('Arrow', ('',))[0]
        if isinstance(arrow, str) and Path(arrow).is_relative_to(self.library):
            style = next((style for style in styles if style.name == name), None)
            if style is not None:
                return style, style.title
        return None, '系统默认' if native_default(values) else 'Windows 当前方案'

    def _store(self, mapping, files, section):
        # Content-based locations keep the selected pointer valid after an update,
        # a portable executable move or the original download being removed.
        digest = hashlib.sha256()
        for name, data in sorted(files.items()):
            digest.update(name.encode('utf-8') + b'\0' + hashlib.sha256(data).digest())
        parent = self.library / section
        parent.mkdir(parents=True, exist_ok=True)
        target = parent / digest.hexdigest()[:24]
        if not target.exists():
            with TemporaryDirectory(dir=parent, prefix='.import-') as workspace:
                stage = Path(workspace) / 'scheme'
                stage.mkdir()
                for name, data in files.items():
                    (stage / name).write_bytes(data)
                try:
                    stage.rename(target)
                except OSError:
                    if not target.is_dir():
                        raise
        if any((target / name).read_bytes() != data for name, data in files.items()):
            raise ValueError('已保存的指针文件损坏。')
        return target, {role: target / file for role, file in mapping.items()}

    def import_style(self, source):
        name, mapping, files = read_pack(Path(source))
        same_name = next((style for style in self.styles() if style.name.casefold() == name.casefold()), None)
        if same_name is not None:
            if read_pack(same_name.source)[2] == files:
                if same_name.source.suffix == '.xz' or same_name.source.is_relative_to(self.library):
                    return same_name
            else:
                raise ValueError('已有同名鼠标方案。')
        folder, _ = self._store(mapping, files, 'imported')
        style = CursorStyle(name, manifest_files(folder)[0])
        self.changed.emit()
        return style

    def apply(self, style):
        if style is None:
            self.system.apply(None, {})
        else:
            name, mapping, files = read_pack(style.source)
            section = 'bundled' if style.source.suffix == '.xz' else 'imported'
            _, paths = self._store(mapping, files, section)
            self.system.apply(name, paths)
        self.changed.emit()
        return style.title if style else '系统默认'

    def cycle(self):
        styles = self.styles()
        current, _ = self.current(styles)
        # The default is the last entry and also the starting state.
        choices = [*styles, None]
        return self.apply(choices[(choices.index(current) + 1) % len(choices)])
