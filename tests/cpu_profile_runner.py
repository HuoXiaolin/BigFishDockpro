"""Profile a private copy of the desktop layout without touching user settings."""
import cProfile
import copy
import io
import json
import math
import os
from pathlib import Path
import pstats
import statistics
import sys
import tempfile
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / name) for name in ('app', 'tests', 'tools')]
if os.environ.get('FISHDOCK_CPU_BASELINE'):
    sys.path.insert(0, str(Path(os.environ['FISHDOCK_CPU_BASELINE']).resolve()))


def main():
    from run_isolated_test import assert_isolated
    desktop = assert_isolated()
    output = Path(sys.argv[-1])
    output.mkdir(parents=True, exist_ok=True)
    from dpi_support import prepare
    prepare()
    from PyQt5.QtCore import QEventLoop, QTimer, Qt
    from PyQt5.QtWidgets import QApplication
    from ui_style import apply_theme, shutdown_ui
    from resource_memory_runner import sample
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    apply_theme(app, True)
    runtime = None
    timers = []
    result = {'stages': [], 'logical_cpus': os.cpu_count() or 1}

    def pump(seconds):
        loop = QEventLoop()
        QTimer.singleShot(round(seconds * 1000), loop.quit)
        loop.exec_()

    def measure(name, seconds=10):
        pump(1)
        readings = []
        previous = [time.perf_counter(), time.process_time()]

        def read():
            now, cpu = time.perf_counter(), time.process_time()
            readings.append(100 * (cpu - previous[1]) / (now - previous[0]) / result['logical_cpus'])
            previous[:] = now, cpu

        timer = QTimer()
        timer.setTimerType(Qt.PreciseTimer)
        timer.timeout.connect(read)
        timer.start(250)
        start, cpu = time.perf_counter(), time.process_time()
        pump(seconds)
        elapsed = time.perf_counter() - start
        consumed = time.process_time() - cpu
        timer.stop()
        values = sorted(readings)
        result['stages'].append(dict(name=name, seconds=round(elapsed, 2),
            cpu_mean=round(100 * consumed / elapsed / result['logical_cpus'], 3),
            cpu_p95=round(values[int(.95 * (len(values) - 1))], 3), cpu_max=round(values[-1], 3),
            memory=sample(os.getpid())))

    try:
        # Imported measurement helpers also prepare sys.path; restore the chosen
        # implementation immediately before the application modules are loaded.
        baseline = os.environ.get('FISHDOCK_CPU_BASELINE')
        if baseline:
            sys.path.insert(0, str(Path(baseline).resolve()))
        import dock as api
        from runtime_controller import RuntimeController
        raw = json.loads((Path(os.environ['APPDATA']) / 'BigFishDock/config.json').read_text(encoding='utf-8-sig'))
        with tempfile.TemporaryDirectory(prefix='bigfish-cpu-') as root:
            api.CONFIG_DIR = root
            api.CONFIG_PATH = str(Path(root) / 'config.json')
            api.LOG_PATH = str(Path(root) / 'dock.log')
            api.RUN_KEY = 'Software\\BigFishDockpro_Test_' + desktop
            cfg = api.normalize_features(copy.deepcopy(raw))
            cfg.update(desktop_icon_mode='both', desktop_auto_sort=False, screen_corners=False,
                       check_updates_on_start=False, hide_tray=True, fullscreen_detection=False,
                       resource_enabled=True, resource_collapsed=True, resource_auto_hide=False)
            dock = api.Dock(cfg, preview=True)
            tray = api.DockTray(dock)
            dock.tray = tray
            runtime = tray.runtime = RuntimeController(dock, tray, api)
            expected = Path(baseline).resolve() if baseline else ROOT / 'app'
            result['implementations'] = {}
            for name in ('resource_compact', 'resource_panel', 'resource_deck'):
                module = __import__(name)
                path = Path(module.__file__).resolve()
                if path.parent != expected:
                    raise RuntimeError('Unexpected benchmark implementation: ' + str(path))
                result['implementations'][name] = str(path)
            pump(1)
            if os.environ.get('FISHDOCK_CPU_RENDER_CHECKS') == '1':
                from resource_render_cache_tests import run
                result['checks'] = []
                run(api, runtime, app, output, result['checks'])
            service = runtime.resources
            window = service.window
            result['dpr'] = window.devicePixelRatioF()

            def readings():
                service.accept_sample(dict(time=time.monotonic(), cpu=23, memory=(64, 9.8, 15.4),
                                           gpu=12, network=(48000, 15000)))
            readings()
            data_timer = QTimer()
            data_timer.timeout.connect(readings)
            data_timer.start(1000)
            timers.append(data_timer)
            result['windows'] = [dict(type=type(w).__name__, size=[w.width(), w.height()])
                                 for w in QApplication.topLevelWidgets() if w.isVisible()]
            measure('collapsed_idle')
            if runtime.spectrum:
                def levels():
                    now = time.monotonic()
                    runtime.spectrum.set_levels([.14 + .48 * abs(math.sin(i * .17 + now * (1 + i % 9 * .14)))
                                                 for i in range(120)])
                spectrum_timer = QTimer()
                spectrum_timer.setTimerType(Qt.PreciseTimer)
                spectrum_timer.timeout.connect(levels)
                spectrum_timer.start(33)
                timers.append(spectrum_timer)
                measure('collapsed_spectrum')
            profile = cProfile.Profile()
            profile.enable()
            pump(8)
            profile.disable()
            stream = io.StringIO()
            pstats.Stats(profile, stream=stream).strip_dirs().sort_stats('tottime').print_stats(55)
            pstats.Stats(profile, stream=stream).strip_dirs().sort_stats('cumulative').print_stats(55)
            (output / 'profile.txt').write_text(stream.getvalue(), encoding='utf-8')
            cfg['resource_collapsed'] = False
            service.sync()
            window.select_page('resources')
            measure('expanded_spectrum')
            result.update(passed=True, scope='Private Windows desktop, copied appearance preferences, synthetic readings and 120-band audio frames, no network or account reads, no working-set trim. CPU timing excludes profiler phase.')
    except Exception:
        result.update(passed=False, error=traceback.format_exc())
    finally:
        for timer in timers:
            timer.stop()
        if runtime:
            runtime.close()
        shutdown_ui(app)
    (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if result.get('passed') else 1


if __name__ == '__main__':
    sys.exit(main())
