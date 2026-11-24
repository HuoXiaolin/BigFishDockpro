"""Exercise scheme selection and restore without writing user cursor settings."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PyQt5.QtWidgets import QMenu

from cursor_styles import BUILTINS, CursorStyles, read_pack
from cursor_style_ui import CursorStylePanel, add_tray_menu
from cursor_windows import AERO_NAME, CursorSystem, ROLES


class MemoryCursorSystem(CursorSystem):
    def __init__(self):
        super().__init__()
        self.values = {'': ('Custom external scheme', 1), 'Arrow': (r'C:\custom\pointer.cur', 2)}
        self.fail_reload = False

    def read(self):
        return self.values.copy()

    def write(self, values):
        self.values = values.copy()

    def reload(self):
        if self.fail_reload:
            self.fail_reload = False
            raise OSError('simulated Windows reload failure')


def run(api, runtime, app, output, checks):
    from dock_extras import DockQuickSettings
    from quick_actions import DEFAULT_ORDER, normalize_order
    from settings_catalog import CURSORS, NOTIFICATIONS, PAGE_GROUPS
    from settings_dialog import SettingsDialog

    assert PAGE_GROUPS[0][1][-2:] == (NOTIFICATIONS, CURSORS)
    prior_order = [key for key in reversed(DEFAULT_ORDER) if key != 'cursor_styles']
    migrated = normalize_order(prior_order)
    assert migrated.index('cursor_styles') == migrated.index('shell_notifications') + 1
    assert [key for key in migrated if key != 'cursor_styles'] == prior_order

    with TemporaryDirectory(prefix='bf-cursor-test-', dir=output) as directory:
        root = Path(directory)
        system = MemoryCursorSystem()
        service = CursorStyles(root, system, local=root / 'user-schemes')
        styles = service.styles()
        amber, ice, *other_styles = styles
        assert [style.name for style in styles[:len(BUILTINS)]] == [name for name, _ in BUILTINS]
        assert {'【玻璃通透】Spirit', '【玻璃通透】Tinted Glass', '【动态个性】Future',
                '【圆润几何】Layan White', '【圆润几何】Phinger Light'} <= {style.name for style in styles}
        assert [style.title for style in styles[:len(BUILTINS)]] == [
            'Bibata 琥珀', 'Bibata 冰白', 'Spirit 玻璃', 'Tinted Glass', 'Future 动态', 'Layan 白色', 'Phinger 浅色']
        for style in other_styles:
            if style.name == 'GrokBot-Soft-Pointer':
                assert style.title == '柔光动态'
        assert len({style.title for style in styles}) == len(styles)
        assert all('【' not in style.title and 'grok' not in style.title.casefold() for style in styles)
        for style in other_styles:
            name, roles, _ = read_pack(style.source)
            assert name == style.name and 'Arrow' in roles
        _, mapping, files = read_pack(amber.source)
        assert set(mapping) == set(ROLES)
        assert mapping['AppStarting'].endswith('.ani') and mapping['Wait'].endswith('.ani')

        incoming = root / 'download'
        incoming.mkdir()
        (incoming / 'normal.cur').write_bytes(files[mapping['Arrow']])
        (incoming / 'person.cur').write_bytes(files[mapping['Person']])
        (incoming / 'pin.cur').write_bytes(files[mapping['Pin']])
        source = incoming / 'Install.inf'
        source.write_text(r'''
[Wreg]
HKCU,"Control Panel\Cursors",Person,0x00020000,"%10%\%person%"
HKCU,"Control Panel\Cursors",Arrow,0x00020000,"%10%\normal.cur"
HKCU,"Control Panel\Cursors",Pin,0x00020000,"%10%\%pin%"
HKCU,"Control Panel\Cursors",CursorBaseSize,0x00010001,999
HKLM,"Control Panel\Cursors",Arrow,0x00020000,"missing.cur"
[Strings]
SCHEME_NAME="本地方案"
person="person.cur"
pin="pin.cur"
''', encoding='utf-8-sig')
        imported = service.import_style(source)
        assert service.import_style(source) == imported
        assert imported.source.parent.is_relative_to(service.library)
        _, parsed, _ = read_pack(imported.source)
        assert parsed == {'Person': 'person.cur', 'Arrow': 'normal.cur', 'Pin': 'pin.cur'}
        for file in incoming.iterdir():
            file.unlink()
        assert service.styles() == [*styles, imported]

        original = system.read()
        system.fail_reload = True
        try:
            service.apply(amber)
        except OSError as error:
            assert 'simulated' in str(error)
        else:
            raise AssertionError('Reload failure must be reported')
        assert system.read() == original
        assert len(list((service.library / 'bundled').iterdir())) == 1

        with patch.object(runtime, 'cursor_styles', service):
            main = SettingsDialog(runtime.tray, api)
            quick = DockQuickSettings(runtime.dock.extras)
            menu = QMenu()
            try:
                main.focus_setting('@cursors')
                assert main.tabs.currentIndex() == CURSORS
                page = main.findChild(CursorStylePanel)
                assert page.current.text().endswith('Windows 当前方案')
                assert page.choices.count() == len(styles) + 1
                assert [page.choices.itemText(index) for index in range(len(styles))] == [
                    style.title for style in styles]
                assert all(not icon.pixmap().isNull() for preview in page.previews for icon in preview)
                page.choices.setCurrentIndex(1)
                page.apply_button.click()
                assert page.current.text().endswith(ice.title)
                page.restore_button.click()
                assert page.current.text().endswith('系统默认')
                assert system.read()[''][0] in (AERO_NAME, '')

                quick.refresh()
                tile = quick.tiles['cursor_styles']
                assert tile.isEnabled() and tile.value == '系统默认'
                for style in (amber, ice, *other_styles, imported):
                    tile.click()
                    assert tile.value == style.title
                    assert page.current.text().endswith(style.title)
                    if style.title == '柔光动态':
                        preview_menu = QMenu()
                        add_tray_menu(preview_menu, runtime)
                        preview_menu.aboutToShow.emit()
                        assert preview_menu.actions()[0].text().endswith('柔光动态')
                        assert system.read()[''][0] == style.name
                        preview_menu.deleteLater()
                add_tray_menu(menu, runtime)
                menu.aboutToShow.emit()
                action = menu.actions()[0]
                assert action.isEnabled() and imported.title in action.text()
                action.trigger()
                choices = service.styles()
                assert service.current(choices) == (None, '系统默认')
                action.trigger()
                assert service.current(choices)[0] == amber
                for role, name in mapping.items():
                    assert Path(system.read()[role][0]).read_bytes() == files[name]

                main.show()
                app.processEvents()
                assert main.grab().save(str(output / 'cursor-styles-settings.png'))
            finally:
                main.close()
                main.deleteLater()
                quick.deleteLater()
                menu.deleteLater()
                app.processEvents()
    checks.append('mouse styles are navigable, preserve CUR/ANI bytes, import role names, cycle through settings and both menus to Windows defaults, and roll back on reload failure')
