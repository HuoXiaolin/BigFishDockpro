"""Source launcher; application code lives in app/."""
from pathlib import Path
import importlib.util
import runpy
import sys

ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/name) for name in ('app','tests','tools')]
if __name__=='__main__':
    runpy.run_path(str(ROOT/'app/dock.py'),run_name='__main__')
else:
    spec=importlib.util.spec_from_file_location(__name__,ROOT/'app/dock.py')
    module=importlib.util.module_from_spec(spec);sys.modules[__name__]=module;spec.loader.exec_module(module)
