"""Bounded native sampling and UI paint work without altering the user desktop."""
import copy,ctypes,json,time,statistics
from ctypes import wintypes as W
from types import SimpleNamespace
from unittest.mock import patch
from PyQt5.QtCore import QTimer


def run(api,runtime,app,output,checks):
    from resource_options import DEFAULTS
    from resource_metrics import PerformanceCounters,CounterItem,busiest_engine
    # Same native-array snapshot, including failed/negative instances.
    names=['pid_1_luid_0x0_0x1_phys_0_eng_0_engtype_3D','pid_2_luid_0x0_0x1_phys_0_eng_0_engtype_3D',
           'pid_3_luid_0x0_0x1_phys_0_eng_1_engtype_Copy','invalid','pid_4_luid_0x0_0x1_phys_0_eng_0_engtype_3D']
    strings=[ctypes.create_unicode_buffer(name) for name in names];items=(CounterItem*len(names))()
    for i,number in enumerate((20,40,12,100,-5)):items[i].name=ctypes.cast(strings[i],W.LPWSTR);items[i].value.status=0;items[i].value.number=number
    def get(handle,flags,size,count,buffer):
        size._obj.value=ctypes.sizeof(items);count._obj.value=len(items)
        if buffer is None:return 0x800007d2
        ctypes.memmove(buffer,ctypes.addressof(items),ctypes.sizeof(items));return 0
    reader=PerformanceCounters.__new__(PerformanceCounters);reader.handles={'engines':1};reader.lib=SimpleNamespace(PdhGetFormattedCounterArrayW=get)
    raw=reader.read('engines');grouped=reader.read('engines',group_engines=True)
    assert len(grouped)==2 and max(grouped.values())==busiest_engine(raw)==60
    cfg=runtime.dock.cfg;before=copy.deepcopy(cfg);service=runtime.resources;job=None;timer=None
    try:
        cfg.update(copy.deepcopy(DEFAULTS));cfg.update(resource_enabled=True,resource_collapsed=True,resource_auto_hide=False,resource_compact_width=560,resource_compact_auto_width=False)
        service.sync();w=service.window;service.accept_sample(dict(time=time.monotonic(),cpu=20,memory=(40,8,16),gpu=15,network=(1000,2000)))
        w.grab()
        with patch('resource_compact._make_plan',wraps=__import__('resource_compact')._make_plan) as rebuild:
            for _ in range(30):w.grab()
            assert rebuild.call_count==0,'Halo frames rebuilt the resident layout'
            w.offset+=1;w.grab();assert rebuild.call_count==1
        service.fold(False);w.select_page('resources');assert {'rank','cpu_cores'}<=service.active_keys()
        cfg['resource_weather']=True;service.sync();w.select_page('weather');assert not {'rank','cpu_cores'}&service.active_keys()
        service.fold(True)
        from resource_capsule import MonitorJob
        class Probe(MonitorJob):
            def run(self):
                kernel=ctypes.windll.kernel32;kernel.GetCurrentThread.restype=W.HANDLE;kernel.GetThreadPriority.argtypes=[W.HANDLE]
                self.priority=kernel.GetThreadPriority(kernel.GetCurrentThread());super().run()
        job=Probe({'cpu','memory','gpu','rank','cpu_cores'},.15);samples=[]
        def receive(data):samples.append(time.perf_counter());service.accept_sample({k:v for k,v in data.items() if k!='rank'})
        job.sample_ready.connect(receive);job.start()
        heartbeat=[];timer=QTimer();timer.setInterval(10);timer.timeout.connect(lambda:heartbeat.append(time.perf_counter()));timer.start()
        paints=[];switches=[];begin=time.perf_counter();next_frame=begin
        while time.perf_counter()-begin<1.6:
            app.processEvents();now=time.perf_counter()
            if now>=next_frame:
                start=time.perf_counter();w.grab();paints.append((time.perf_counter()-start)*1000);next_frame=now+1/60
            time.sleep(.001)
        for key in ('resources','traffic','weather','resources'):
            start=time.perf_counter();service.fold(False);w.select_page(key);app.processEvents();switches.append((time.perf_counter()-start)*1000)
        timer.stop();job.requestInterruption();assert job.wait(4000) and job.priority==-1
        assert len(paints)>10 and len(heartbeat)>10 and len(samples)>1
        # Cache reclamation must leave interactive dialogs untouched.
        from PyQt5.QtWidgets import QDialog
        dialog=QDialog();dialog.show();app.processEvents()
        try:
            with patch('memory_budget.release_unused_heap') as release:
                assert not runtime.memory_budget.reclaim() and dialog.isVisible()
                release.assert_not_called()
        finally:dialog.close();dialog.deleteLater();app.processEvents()
        def metrics(values):
            values=sorted(values);return dict(median_ms=round(statistics.median(values),2),p95_ms=round(values[min(len(values)-1,int(len(values)*.95))],2),max_ms=round(max(values),2))
        result=dict(passed=True,paint=metrics(paints),page_switch=metrics(switches),heartbeat=metrics([(b-a)*1000 for a,b in zip(heartbeat,heartbeat[1:])]),
                    samples=len(samples),dpr=w.devicePixelRatioF(),frames=len(paints),worker_priority=job.priority,
                    scope='Private desktop; real native counters on a background thread, 60 Hz requested rendering, no foreground interaction or playback commands. Timing is a local sample, not a cross-device guarantee.')
        (output/'resource-responsiveness.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        checks.append('Performance: native GPU aggregation equals per-instance totals, avoids duplicate instance maps; unchanged animation frames reuse compact layout, hidden resource page stops rank/core counters; real sampling runs below-normal in its worker while Qt heartbeat/paint/page changes continue. Timing report captured without working-set trim.')
    finally:
        if timer:timer.stop()
        if job:job.requestInterruption();job.wait(4000);job.deleteLater()
        cfg.clear();cfg.update(before);service.sync();api.save_config(cfg)
