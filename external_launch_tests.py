"""Native DLL lifetime checks, confined to temporary fixtures and an isolated desktop."""
import ctypes
import os
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch
from desktop_panel_tests import wait_for


def run(api,runtime,root,output,checks):
    from PyQt5.QtWidgets import QApplication
    import external_launch
    app=QApplication.instance()
    folder=Path(root)/'dll-launch';folder.mkdir()
    bundle=folder/'_MEI_owned_fixture';bundle.mkdir()
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetDllDirectoryW.argtypes=[ctypes.c_uint,ctypes.c_wchar_p]
    kernel.SetDllDirectoryW.argtypes=[ctypes.c_wchar_p]
    previous=ctypes.create_unicode_buffer(32768);kernel.GetDllDirectoryW(len(previous),previous)
    old_path=os.environ['PATH'];old_qt=os.environ.get('QT_PLUGIN_PATH')
    original_meipass=getattr(sys,'_MEIPASS',None)
    try:
        kernel.SetDllDirectoryW(str(bundle));sys._MEIPASS=str(bundle)
        os.environ['PATH']=str(bundle)+os.pathsep+old_path
        os.environ['QT_PLUGIN_PATH']=str(bundle/'Qt/plugins')
        captured=[]
        def shell(path,**kwargs):
            now=ctypes.create_unicode_buffer(32768);kernel.GetDllDirectoryW(len(now),now)
            captured.append((now.value,dict(os.environ),kwargs));raise OSError('simulated launch failure')
        with patch.object(os,'startfile',side_effect=shell):
            try:external_launch.startfile('https://example.com')
            except OSError:pass
        assert captured and not captured[0][0] and str(bundle) not in captured[0][1]['PATH']
        assert 'QT_PLUGIN_PATH' not in captured[0][1]
        assert captured[0][1]['PYINSTALLER_RESET_ENVIRONMENT']=='1'
        now=ctypes.create_unicode_buffer(32768);kernel.GetDllDirectoryW(len(now),now)
        assert now.value==str(bundle) and os.environ['QT_PLUGIN_PATH']==str(bundle/'Qt/plugins')
        fixture=os.environ.get('FISHDOCK_NATIVE_LAUNCH_FIXTURE')
        if fixture:
            crt=Path(os.environ['WINDIR'])/'System32/VCRUNTIME140_1.dll'
            assert crt.is_file(),'Native fixture needs installed system CRT'
            copied=bundle/crt.name;shutil.copy2(crt,copied)
            for clean in (False,True):
                executable=folder/('clean.exe' if clean else 'inherited.exe');shutil.copy2(fixture,executable)
                process=None
                try:
                    process=external_launch.launch(str(executable)) if clean else subprocess.Popen([str(executable)],close_fds=True)
                    report=Path(str(executable)+'.library.txt')
                    wait_for(app,lambda:report.exists() and report.stat().st_size>0,5)
                    actual=report.read_text(encoding='utf-8')
                    assert (str(bundle).casefold() in actual.casefold()) is not clean,actual
                    if not clean:
                        try:copied.unlink()
                        except OSError:pass
                        else:raise AssertionError('Dirty child must retain the bundled runtime')
                    else:
                        copied.unlink();assert process.poll() is None
                finally:
                    Path(str(executable)+'.stop').touch()
                    if process is not None:assert process.wait(timeout=8)==0
            checks.append('exit cleanup native reproduction: unsanitized external child locks bundled CRT; clean launch loads system CRT and bundled copy can be removed while child stays alive')
        checks.append('external launch: DLL directory, PATH and Qt paths sanitized for ShellExecute/subprocess and restored on exceptions; independent frozen environment and stable working directory')
    finally:
        kernel.SetDllDirectoryW(previous.value or None)
        os.environ['PATH']=old_path
        if old_qt is None:os.environ.pop('QT_PLUGIN_PATH',None)
        else:os.environ['QT_PLUGIN_PATH']=old_qt
        if original_meipass is None:del sys._MEIPASS
        else:sys._MEIPASS=original_meipass
