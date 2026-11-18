"""The fast profile must never silently cover unrelated runtime changes."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from build_plan import classify


class BuildPlanTests(unittest.TestCase):
    def test_shell_and_pipeline_changes(self):
        self.assertEqual(classify(['tools/ShellAppearance/start_layout.h',
                                   'app/shell_appearance_model.py', 'tools/build.ps1',
                                   'docs/系统面板外观.md'], True), 'shell')

    def test_unknown_runtime_change_expands_checks(self):
        for path in ('app/resources.py', 'tools/BigFishDockpro.spec', 'assets/app.ico',
                     'tools/release_tools.py', 'references/ShellStyler/start.wh.cpp'):
            self.assertEqual(classify(['tools/ShellAppearance/start_layout.h', path], True), 'runtime')

    def test_no_verified_baseline(self):
        self.assertEqual(classify(['tools/ShellAppearance/start_layout.h'], False), 'runtime')

    def test_pipeline_only_or_no_change_keeps_runtime(self):
        self.assertEqual(classify(['tools/build.ps1'], True), 'runtime')
        self.assertEqual(classify([], True), 'runtime')


if __name__ == '__main__':
    unittest.main()
