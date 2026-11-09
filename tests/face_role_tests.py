"""Role package import, settings persistence and native SVG rendering."""
import copy
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from PyQt5.QtCore import QPoint, QPointF, Qt
from PyQt5.QtGui import QCursor, QImage, QPainter
from PyQt5.QtWidgets import QApplication, QFileDialog, QPushButton

SVG_START = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
BACK = SVG_START + """
<defs><linearGradient id="hood" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="#81d8f8"/><stop offset="1" stop-color="#4469ce"/>
</linearGradient></defs>
<path d="M15 40Q7 37 4 26Q13 24 23 31Q30 18 43 17Q42 9 49 6Q58 10 61 18Q83 20 90 39Q98 37 98 44Q96 52 89 52L89 67Q87 91 50 94Q13 91 13 68Z" fill="url(#hood)"/>
<path d="M22 55Q21 32 50 31Q79 32 79 55L82 73Q75 88 50 88Q25 88 18 73Z" fill="#fdf3eb"/>
<path d="M22 56Q23 42 29 41L28 72Q23 76 21 73Z M77 56Q76 42 70 41L72 72Q77 76 79 73Z" fill="#2a4f98"/>
</svg>"""
FRONT = SVG_START + """
<path d="M25 49Q23 29 53 30Q77 32 76 49Q57 45 47 38Q38 46 25 49Z" fill="#334777"/>
<path d="M33 28Q41 19 55 21L55 27Q42 26 33 32Z" fill="#fff6cc"/>
</svg>"""


def make_package(folder, role_id, name, front=True):
    folder.mkdir()
    manifest = dict(version=1, id=role_id, name=name, layers={'back': 'body.svg'},
                    anchors={'left_eye': [36, 58], 'right_eye': [64, 58], 'mouth': [50, 72]}, ink='#20355e')
    (folder/'body.svg').write_text(BACK, encoding='utf-8')
    if front:
        manifest['layers']['front'] = 'front.svg'
        (folder/'front.svg').write_text(FRONT, encoding='utf-8')
    path = folder/'manifest.json'
    path.write_text(json.dumps(manifest), encoding='utf-8')
    return path


def click(dialog, text):
    next(button for button in dialog.findChildren(QPushButton) if button.text() == text).click()


def assert_capture(widget, tracker, role, path=None):
    with patch.object(tracker, 'paint_role', wraps=tracker.paint_role) as paint:
        pixmap = widget.grab()
    assert paint.called and paint.call_args.args[1] == role
    if path:
        assert pixmap.save(str(path))


def check_invalid_import(library, manifest, original):
    package = json.loads(manifest.read_text(encoding='utf-8'))
    body = manifest.with_name('body.svg')
    for changed, svg in (
        (dict(package, layers={'back': '../body.svg'}), BACK),
        (dict(package, anchors={'left_eye': [101, 24]}), BACK),
        (package, SVG_START + '<script/><circle cx="50" cy="50" r="40"/></svg>'),
        (package, SVG_START + '<rect width="1e1000" height="50"/></svg>'),
        (package, SVG_START + '<rect width="100" height="100"/></svg>'),
    ):
        manifest.write_text(json.dumps(changed), encoding='utf-8')
        body.write_text(svg, encoding='utf-8')
        try:
            library.import_package(manifest)
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid role package was imported')
        assert library.get(package['id']) == original
    manifest.write_text(json.dumps(package), encoding='utf-8')
    body.write_text(BACK, encoding='utf-8')


def check_layers(tracker, role):
    image = QImage(100, 100, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    tracker.paint_role(painter, role, QPointF(50, 50), 100, QPointF(),
                       {'light': True, 'ink': '#102230'}, False)
    painter.end()
    assert image.pixelColor(1, 1).alpha() == 0
    assert image.pixelColor(47, 23).name() == '#fff6cc'
    assert image.pixelColor(36, 58).name() != image.pixelColor(45, 58).name()


def run(api, runtime, app, output, checks):
    from face_roles import RoleLibrary
    from face_role_controls import ROLE_PROMPT
    from glass_panel import PanelOptions
    from resource_settings import ResourceOptions
    from settings_dialog import SettingsDialog
    cfg = runtime.dock.cfg
    before = copy.deepcopy(cfg)
    service = runtime.resources
    dialogs = []
    try:
        with tempfile.TemporaryDirectory(prefix='fishdock-role-test-') as folder:
            base = Path(folder)
            whale = make_package(base/'whale', 'whale-girl', '鲸鱼女孩')
            star = make_package(base/'star', 'star-girl', '星帽女孩', front=False)
            library = runtime.face_roles
            assert library.get('whale-girl') is None and not library.choices()
            cfg.update(resource_enabled=True, resource_collapsed=True, resource_fold='pill',
                       resource_auto_hide=False, resource_face=True, resource_face_interactive=True,
                       resource_face_mood='default', resource_face_role='', resource_weather=False,
                       resource_ai=False, resource_music=False, resource_ai_tray=False, resource_news=False,
                       resource_compact_metrics=['cpu', 'memory', 'gpu', 'network'],
                       resource_compact_pinned=['cpu', 'memory', 'gpu', 'network'],
                       resource_compact_order=['cpu', 'memory', 'gpu', 'network'],
                       resource_taskbar=False, panel_enabled=True, panels_visible=True,
                       panel_auto_hide=False, panel_face=True, panel_face_interactive=True,
                       panel_face_mood='default', panel_face_role='', motion_enabled=True)
            runtime.apply_settings()
            app.processEvents()
            capsule = service.window
            panel = next(window for window in runtime.panels.windows.values() if window.isVisible())
            panel.set_collapsed_geometry(False)
            resource_options = ResourceOptions(service)
            dialogs.append(resource_options)
            resource_options.tabs.setCurrentIndex(6)
            picker = resource_options.fields['resource_face_role']
            assert picker.currentData() == ''
            clipboard = Mock()
            with patch.object(QApplication, 'clipboard', return_value=clipboard):
                click(resource_options, '复制提示词')
            clipboard.setText.assert_called_once_with(ROLE_PROMPT)
            assert all(key in ROLE_PROMPT for key in ('manifest.json', 'body.svg', 'left_eye', 'right_eye', 'mouth'))
            with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(whale), '')):
                click(resource_options, '导入角色包…')
            assert picker.currentData() == 'whale-girl' and cfg['resource_face_role'] == ''
            resource_options.tabs.setCurrentIndex(0)
            resource_options.tabs.setCurrentIndex(6)
            assert resource_options.fields['resource_face_role'].currentData() == 'whale-girl'
            assert resource_options.commit()
            role = library.get('whale-girl')
            assert role and RoleLibrary(api.CONFIG_DIR).get('whale-girl') == role
            check_invalid_import(library, whale, role)
            check_layers(capsule.liquid, role)
            with patch.dict(service.latest, cpu=18, memory=(64, 10307921510, 16106127360),
                            gpu=27, network=(384 * 1024, 82 * 1024)):
                capsule.refresh()
                assert_capture(capsule, capsule.liquid, role, output/'readme-face-role.png')
            assert service.set_options(resource_fold='ball')
            assert_capture(capsule, capsule.liquid, role, output/'face-role-ball.png')
            capsule.liquid.face.ex.x = 0
            direction = capsule.mapToGlobal(capsule.rect().center()+QPoint(850, 500))
            with patch.object(QCursor, 'pos', return_value=direction):
                for _ in range(14):
                    capsule.liquid.face._t -= .033
                    capsule.grab()
            assert capsule.liquid.face.ex.x > .5 and capsule.liquid.face.ey.x > .25
            assert service.fold(False)
            assert_capture(capsule, capsule.liquid, role, output/'face-role-expanded.png')

            options = PanelOptions(panel)
            dialogs.append(options)
            assert options.fields['face_role'].findData('whale-girl') >= 0
            with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(star), '')):
                click(options, '导入角色包…')
            assert options.commit()
            assert_capture(panel, panel.face_tracker, library.get('star-girl'), output/'face-role-panel.png')
            saved = api.load_config()
            assert saved['resource_face_role'] == 'whale-girl' and saved['panel_face_role'] == 'star-girl'
            main = SettingsDialog(runtime.tray, api)
            dialogs.append(main)
            assert main.fields['panel_face_role'].currentData() == 'star-girl'
            main.set_draft_values({'panel_face_role': 'missing-role'})
            assert main.fields['panel_face_role'].currentText().startswith('缺少角色包')
            assert library.get('missing-role') is None
            revised = json.loads(whale.read_text(encoding='utf-8'))
            revised['name'] = '鲸鱼女孩 · 新版'
            whale.write_text(json.dumps(revised), encoding='utf-8')
            with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(whale), '')):
                click(resource_options, '导入角色包…')
            assert ('鲸鱼女孩 · 新版', 'whale-girl') in library.choices()
            assert_capture(capsule, capsule.liquid, library.get('whale-girl'))
            assert service.set_options(resource_face_role='missing-role')
            with patch.object(capsule.liquid, 'paint_role') as paint:
                capsule.grab()
                paint.assert_not_called()
            assert capsule.liquid.face is not None
    finally:
        for dialog in reversed(dialogs):
            dialog.reject()
            dialog.deleteLater()
        cfg.clear()
        cfg.update(before)
        runtime.apply_settings()
        api.save_config(cfg)
        app.processEvents()
    checks.append('Local SVG role packages import from both settings surfaces, keep independent selections and survive a library reload.')
    checks.append('Role SVG layers and facial anchors render with transparent pixels; imported faces track the cursor in the ball and display in compact, expanded and desktop views.')
    checks.append('The prompt copies, missing roles fall back to the built-in face and invalid replacements preserve the installed role.')
