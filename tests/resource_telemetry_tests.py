"""Regressions for 2.4G battery states and independently resettable traffic ledgers."""
from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from resource_app_traffic import AppTrafficHistory, add_interval, frame_rows
from resource_peripherals import (bind_profiles, diagnostics_prompt, format_reading, load_profile_file,
                                  merge_readings, normalize_profiles, save_diagnostics,
                                  save_diagnostics_prompt, save_profile_file)
from resource_traffic import TrafficLedger


def run(checks):
    profile = dict(device_id='a' * 32, name='Fixture receiver', protocol='compx-power',
                   vid=0x3554, pid=0xf58a, usage_page=0xff02, usage=2, input=17,
                   output=17, feature=0, revision=1, interface=1, collection=2)
    portable = {key:value for key,value in profile.items() if key!='device_id'}
    assert bind_profiles([portable],[profile]) == [profile]
    try:
        bind_profiles([portable],[dict(profile,protocol=None)])
    except ValueError:
        pass
    else:
        raise AssertionError('Unknown receiver accepted an imported protocol')
    received = dict(id=profile['device_id'],name=profile['name'])
    charged = merge_readings([profile],[dict(received,state='charging',level=62)])
    sleeping = merge_readings([profile],[dict(received,state='sleeping',level=0)],charged)
    assert '62%' in format_reading(charged[0]) and '充电中' in format_reading(charged[0])
    assert sleeping[0]['stale'] and '上次 62%' in format_reading(sleeping[0]) and '休眠' in format_reading(sleeping[0])
    timeout = merge_readings([profile],[],sleeping)
    assert timeout[0]['state']=='unavailable' and timeout[0]['level']==62
    active = merge_readings([profile],[dict(received,state='active',level=0)],timeout)
    assert active[0]['level']==0 and not active[0]['stale']
    checks.append('2.4G profiles reject an unknown protocol; charging, explicit sleep, timeout and real 0% stay distinct.')

    alias='书桌鼠标'
    named=normalize_profiles([dict(profile,alias=' '+alias+' ')],strict=True)
    assert named[0]['name']==profile['name'] and named[0]['device_id']==profile['device_id']
    assert merge_readings(named,[dict(received,state='charging',level=62)])[0]['name']==alias
    with TemporaryDirectory(prefix='fishdock-peripheral-prompt-') as directory:
        root=Path(directory)
        device=dict(profile,alias=alias)
        unavailable=dict(profile,device_id='b'*32,pid=0xffff,protocol=None)
        diagnostic=root/'peripheral-diagnostics.json'
        save_diagnostics(diagnostic,[unavailable,device])
        raw=diagnostic.read_text(encoding='utf-8')
        assert len(json.loads(raw)['devices'])==2 and not any(item in raw for item in (
            profile['device_id'],unavailable['device_id'],alias,'receiver_id'))
        prompt=diagnostics_prompt([unavailable,device],device['device_id'],diagnostic.name)
        assert '第 2 条' in prompt and 'compx-power' in prompt and 'peripheral-profiles.json' in prompt
        assert device['device_id'] not in prompt and alias not in prompt
        assert '两种协议字段都缺失' in diagnostics_prompt([unavailable],unavailable['device_id'])
        companion=save_diagnostics_prompt(diagnostic,prompt)
        another=save_diagnostics_prompt(diagnostic,'different prompt')
        assert companion!=another and companion.read_text(encoding='utf-8')==prompt
        exported=root/'peripheral-profiles.json'
        save_profile_file(exported,named)
        assert bind_profiles(load_profile_file(exported),[profile])==named
    checks.append('2.4G diagnostic prompts select a redacted interface and request the import format; aliases round-trip without changing receiver identity.')

    with TemporaryDirectory(prefix='fishdock-traffic-ledgers-') as directory:
        root=Path(directory)
        total=TrafficLedger(root/'total.json')
        today=date.today()
        now=datetime.combine(today,time(0,0,1))
        total.add(today.isoformat(),[800,200])
        total.flush()
        history_path=root/'apps.sqlite3'
        rows,elapsed=frame_rows({'elapsed':2,'rows':[
            dict(id='browser',name='Browser',down=60,up=10),
            dict(id='browser',name='Browser',down=40,up=10),
            dict(id='editor',name='Editor',down=30,up=0)]})
        history=AppTrafficHistory(history_path)
        try:
            add_interval(history,rows,elapsed,now)
            assert history.flush()
            assert history.history('day')==[('Browser',50,10),('Editor',15,0)]
            assert history.history('all')==[('Browser',100,20),('Editor',30,0)]
            total.observe({'eth':(1000,2000)},now)
            assert total.reset()['days']=={}
            assert history.history('all')[0]==('Browser',100,20)
            assert total.observe({'eth':(1010,2010)},now+timedelta(seconds=1))['day']==(0,0)
            assert total.observe({'eth':(1015,2020)},now+timedelta(seconds=2))['day']==(5,10)
            total.flush()
        finally:
            history.close()
        reopened=AppTrafficHistory(history_path)
        try:
            assert reopened.history('all')[0]==('Browser',100,20)
            assert reopened.reset() and reopened.history('all')==[]
            assert TrafficLedger(total.path).snapshot()['day']==(5,10)
        finally:
            reopened.close()
    checks.append('Traffic ranks merge app deltas, preserve midnight totals across reopen, and reset each ledger independently with a fresh network baseline.')
