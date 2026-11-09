"""Import local, static SVG skins for the shared face animation."""
import hashlib
import json
import math
import re
from dataclasses import dataclass
from functools import cached_property, lru_cache
from pathlib import Path

MANIFEST_LIMIT = 8 * 1024
SVG_LIMIT = 64 * 1024
RECORD_LIMIT = MANIFEST_LIMIT + 4 * SVG_LIMIT
MAX_ROLES = 32
SVG_NS = 'http://www.w3.org/2000/svg'
ROLE_ID = re.compile(r'[a-z][a-z0-9-]{0,39}')
COLOR = re.compile(r'#[0-9a-fA-F]{6}')
NUMBER = re.compile(r'[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?')
SHAPES = {
    'svg': {'viewBox', 'width', 'height'},
    'g': set(), 'defs': set(), 'title': set(), 'desc': set(),
    'path': {'d'}, 'rect': {'x', 'y', 'width', 'height', 'rx', 'ry'},
    'circle': {'cx', 'cy', 'r'}, 'ellipse': {'cx', 'cy', 'rx', 'ry'},
    'line': {'x1', 'y1', 'x2', 'y2'}, 'polyline': {'points'}, 'polygon': {'points'},
    'linearGradient': {'x1', 'y1', 'x2', 'y2', 'gradientUnits', 'gradientTransform', 'spreadMethod'},
    'radialGradient': {'cx', 'cy', 'r', 'fx', 'fy', 'gradientUnits', 'gradientTransform', 'spreadMethod'},
    'stop': {'offset', 'stop-color', 'stop-opacity'},
}
PAINT = {
    'id', 'fill', 'fill-opacity', 'fill-rule', 'opacity', 'stroke', 'stroke-opacity',
    'stroke-width', 'stroke-linecap', 'stroke-linejoin', 'stroke-miterlimit',
    'stroke-dasharray', 'stroke-dashoffset', 'transform',
}
GEOMETRY = {
    'd', 'points', 'transform', 'gradientTransform', 'x', 'y', 'x1', 'x2', 'y1', 'y2',
    'cx', 'cy', 'r', 'rx', 'ry', 'fx', 'fy', 'width', 'height',
    'stroke-width', 'stroke-dasharray', 'stroke-dashoffset', 'stroke-miterlimit',
}
REFERENCED_PAINT = re.compile(r'url\(\s*#[A-Za-z_][\w.-]*\s*\)', re.ASCII)


def clean_role_id(value, strict=False):
    if isinstance(value, str) and (not value or ROLE_ID.fullmatch(value)):
        return value
    if strict:
        raise ValueError('角色标识须以小写字母开头，最多 40 个小写字母、数字或连字符。')
    return ''


def read_limited(path, limit):
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f'{path.name} 超过 {limit // 1024} KiB。')
    return data


def parse_manifest(value):
    if not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != 1:
        raise ValueError('manifest.json 须使用 version 为 1 的角色清单。')
    role_id = clean_role_id(value.get('id'), strict=True)
    name = value.get('name')
    if not role_id or not isinstance(name, str) or not 1 <= len(name.strip()) <= 32 or not name.isprintable():
        raise ValueError('请填写非空角色标识和 1 至 32 字的角色名称。')
    layers = value.get('layers')
    if not isinstance(layers, dict) or set(layers) not in ({'back'}, {'back', 'front'}):
        raise ValueError('layers 须包含 back，可再指定 front。')
    for filename in layers.values():
        if (not isinstance(filename, str) or not filename.isprintable() or
                not re.fullmatch(r'[^/\\:<>|"?*]+\.svg', filename, re.IGNORECASE)):
            raise ValueError('图层须填写与 manifest.json 同目录的 SVG 文件名。')
    raw = value.get('anchors')
    keys = ('left_eye', 'right_eye', 'mouth')
    if not isinstance(raw, dict) or any(
        not isinstance(point := raw.get(key), list) or len(point) != 2 or
        any(type(n) not in (int, float) or not 0 <= n <= 100 for n in point)
        for key in keys
    ):
        raise ValueError('anchors 须填写 left_eye、right_eye 和 mouth，各为两个 0 至 100 的坐标。')
    if raw['left_eye'][0] >= raw['right_eye'][0]:
        raise ValueError('left_eye 须位于 right_eye 左边，以屏幕方向为准。')
    ink = value.get('ink', '')
    if not isinstance(ink, str) or (ink and not COLOR.fullmatch(ink)):
        raise ValueError('ink 须为 #RRGGBB 颜色，留空时跟随应用主题。')
    return dict(version=1, id=role_id, name=name.strip(), layers=layers,
                anchors={key: raw[key] for key in keys}, ink=ink.lower())


def safe_svg(svg, filename):
    from xml.etree import ElementTree
    if re.search(r'<!\s*(DOCTYPE|ENTITY)', svg, re.IGNORECASE):
        raise ValueError(f'{filename} 不能使用 DTD 或实体声明。')
    try:
        root = ElementTree.fromstring(svg)
    except ElementTree.ParseError as error:
        raise ValueError(f'{filename} 的 SVG 无法解析。') from error
    if root.tag != f'{{{SVG_NS}}}svg' or re.split(r'[\s,]+', root.get('viewBox', '').strip()) != ['0', '0', '100', '100']:
        raise ValueError(f'{filename} 须使用 SVG 命名空间和 viewBox="0 0 100 100"。')
    pending = [(root, 0)]
    count = 0
    while pending:
        element, depth = pending.pop()
        count += 1
        if count > 512 or depth > 20:
            raise ValueError(f'{filename} 的图形或嵌套层级太多。')
        tag = element.tag.removeprefix(f'{{{SVG_NS}}}')
        if tag not in SHAPES or (tag == 'svg' and depth):
            raise ValueError(f'{filename} 含不支持的元素 {tag.rsplit("}", 1)[-1]}。')
        if tag in ('title', 'desc'):
            element.text = None
        if (element.text or '').strip() or (element.tail or '').strip():
            raise ValueError(f'{filename} 须使用矢量形状绘制内容。')
        for attr, value in element.attrib.items():
            if attr not in SHAPES[tag] and attr not in PAINT:
                raise ValueError(f'{filename} 含不支持的属性 {attr.rsplit("}", 1)[-1]}。')
            if attr in ('fill', 'stroke') and '(' in value and not REFERENCED_PAINT.fullmatch(value.strip()):
                # Qt SVG also supports ordinary rgb() paint values.
                if not re.fullmatch(r'rgba?\([0-9.%,\s]+\)', value.strip()):
                    raise ValueError(f'{filename} 的渐变只能引用本文件内的 ID。')
            if attr in GEOMETRY:
                if any(not math.isfinite(n) or abs(n) > 10000 for n in map(float, NUMBER.findall(value))):
                    raise ValueError(f'{filename} 含超出范围的图形坐标。')
        element.tag = tag
        pending.extend((child, depth + 1) for child in element)
    root.set('xmlns', SVG_NS)
    root.set('width', '100')
    root.set('height', '100')
    return ElementTree.tostring(root, encoding='unicode')


def validate_render(svg, filename):
    from PyQt5.QtCore import QByteArray, QRectF, Qt
    from PyQt5.QtGui import QImage, QPainter
    from PyQt5.QtSvg import QSvgRenderer
    renderer = QSvgRenderer(QByteArray(svg.encode('utf-8')))
    if not renderer.isValid():
        raise ValueError(f'{filename} 无法绘制。')
    image = QImage(48, 48, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    renderer.render(painter, QRectF(image.rect()))
    painter.end()
    alphas = [image.pixel(x, y) >> 24 for y in range(48) for x in range(48)]
    if max(alphas) == 0 or min(alphas) == 255:
        raise ValueError(f'{filename} 须包含可见图形和透明背景。')


@dataclass(frozen=True)
class FaceRole:
    anchors: tuple
    ink: str
    back: str
    front: str
    digest: str


class RoleLibrary:
    def __init__(self, config_dir):
        self.directory = Path(config_dir) / 'face-roles'
        self.get = lru_cache(maxsize=4)(self._load)

    def path(self, role_id):
        return self.directory / f'role-{role_id}.json'

    def _records(self):
        return self.directory.glob('role-*.json')

    def import_package(self, manifest_path):
        from config_store import _atomic
        source = Path(manifest_path)
        if source.name.lower() != 'manifest.json':
            raise ValueError('请选择角色包的 manifest.json。')
        try:
            raw = json.loads(read_limited(source, MANIFEST_LIMIT).decode('utf-8-sig'))
        except json.JSONDecodeError as error:
            raise ValueError(f'manifest.json 第 {error.lineno} 行、第 {error.colno} 列的 JSON 格式有误。') from error
        except (UnicodeError, RecursionError) as error:
            raise ValueError('manifest.json 须为有效的 UTF-8 JSON。') from error
        manifest = parse_manifest(raw)
        target = self.path(manifest['id'])
        if not target.exists() and sum(1 for _ in self._records()) >= MAX_ROLES:
            raise ValueError(f'最多可导入 {MAX_ROLES} 个角色。')
        folder = source.parent.resolve()
        layers = {}
        for layer, filename in manifest['layers'].items():
            path = (folder / filename).resolve()
            if path.parent != folder or not path.is_file():
                raise ValueError(f'请将 {filename} 放在 manifest.json 同一文件夹。')
            try:
                svg = read_limited(path, SVG_LIMIT).decode('utf-8-sig')
            except UnicodeError as error:
                raise ValueError(f'{filename} 须为 UTF-8 SVG。') from error
            layers[layer] = safe_svg(svg, filename)
            validate_render(layers[layer], filename)
        payload = json.dumps(dict(manifest=manifest, svg=layers), ensure_ascii=False).encode('utf-8')
        if len(payload) > RECORD_LIMIT:
            raise ValueError('角色包内容过大。')
        _atomic(target, payload)
        self.get.cache_clear()
        self.__dict__.pop('_choices', None)
        return manifest['id']

    @staticmethod
    def _record(path):
        payload = read_limited(path, RECORD_LIMIT)
        raw = json.loads(payload)
        if not isinstance(raw, dict):
            raise ValueError('角色记录无效。')
        manifest = parse_manifest(raw.get('manifest'))
        if path.name != f'role-{manifest["id"]}.json':
            raise ValueError('角色记录的标识无效。')
        return manifest, raw.get('svg'), payload

    def choices(self):
        return self._choices

    @cached_property
    def _choices(self):
        choices = []
        for path in self._records():
            try:
                manifest, _, _ = self._record(path)
            except (OSError, ValueError, RecursionError):
                continue
            choices.append((manifest['name'], manifest['id']))
        return tuple(sorted(choices))

    def _load(self, role_id):
        if not clean_role_id(role_id):
            return None
        try:
            manifest, layers, payload = self._record(self.path(role_id))
            if not isinstance(layers, dict) or layers.keys() != manifest['layers'].keys():
                return None
            checked = {key: safe_svg(svg, key) for key, svg in layers.items()
                       if isinstance(svg, str) and len(svg) <= 2 * SVG_LIMIT}
            if checked.keys() != layers.keys():
                return None
        except (OSError, ValueError, RecursionError):
            return None
        return FaceRole(tuple(tuple(point) for point in manifest['anchors'].values()),
                        manifest['ink'], checked['back'], checked.get('front', ''),
                        hashlib.sha256(payload).hexdigest())
