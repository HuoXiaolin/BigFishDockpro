"""Private-desktop A/B test. Records bytes for the probe process only."""
import copy, ctypes, json, os, statistics, time
from ctypes import wintypes
from unittest.mock import patch


class Memory(ctypes.Structure):
    _fields_=[("cb",wintypes.DWORD),("PageFaultCount",wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in
        ("PeakWorkingSetSize","WorkingSetSize","QuotaPeakPagedPoolUsage","QuotaPagedPoolUsage","QuotaPeakNonPagedPoolUsage","QuotaNonPagedPoolUsage","PagefileUsage","PeakPagefileUsage","PrivateUsage","PrivateWorkingSetSize")]+[("SharedCommitUsage",ctypes.c_ulonglong)]


def measure(runtime,app):
    from run_isolated_test import assert_isolated
    from resource_options import DEFAULTS,METRICS
    assert_isolated()
    kernel=ctypes.WinDLL("kernel32",use_last_error=True)
    fn=kernel.K32GetProcessMemoryInfo
    fn.argtypes=[wintypes.HANDLE,ctypes.POINTER(Memory),wintypes.DWORD]
    def sample():
        record=Memory();record.cb=ctypes.sizeof(record)
        if not fn(wintypes.HANDLE(-1),ctypes.byref(record),record.cb) or record.PrivateWorkingSetSize==0:raise RuntimeError("Private working set unavailable")
        return [round(v/2**20,2) for v in (record.PrivateWorkingSetSize,record.WorkingSetSize,record.PrivateUsage)]
    def pump(seconds):
        until=time.monotonic()+seconds
        while time.monotonic()<until:
            app.processEvents();time.sleep(.025)
    cfg=runtime.dock.cfg;original=copy.deepcopy(cfg);service=runtime.resources
    old_game=runtime.game_active
    phases=[]
    try:
        runtime.game_active=False
        cfg.update(copy.deepcopy(DEFAULTS));cfg.update(resource_enabled=True,resource_collapsed=False,resource_auto_hide=False,resource_interval=1,resource_rank=False)
        start=service.start_job
        # Use production OS counters while keeping UI placement and desktop changes isolated.
        def start_reader():
            with patch.object(runtime.dock,"preview",False):start()
        with patch.object(service,"start_job",start_reader):
            for name,enabled in (("off-1",False),("on-1",True),("off-2",False),("on-2",True),("off-3",False)):
                cfg["resource_rank"]=enabled;service.sync();pump(2.4)
                rows=[]
                for _ in range(4):
                    pump(.40);rows.append(sample())
                ranked=service.latest.get("rank") or {}
                assert service.job and bool(ranked.get("memory"))==enabled,(name,service.signature)
                phases.append(dict(name=name,median=[round(statistics.median(col),2) for col in zip(*rows)],samples=rows))
            initial_job=service.job
            transitions=[]
            for folded in (True,False,True,False):
                cfg['resource_collapsed']=folded;service.sync()
                assert service.job is initial_job and 'cpu' in service.latest and service.latest.get('network') is not None
                pump(.30)
                assert service.job is initial_job and 'cpu' in service.latest and service.latest.get('network') is not None
                transitions.append(folded)
        return dict(passed=True,continuous_folds=transitions,columns=["private_working_set_MiB","working_set_MiB","private_commit_MiB"],phases=phases,seconds_per_phase=4.0,metrics="CPU, cores, memory, network and GPU enabled throughout; rank-only toggle",frozen=bool(getattr(__import__("sys"),"frozen",False)))
    finally:
        cfg.clear();cfg.update(original);runtime.game_active=old_game;service.sync()
