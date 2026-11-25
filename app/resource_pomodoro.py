"""Focus and hydration deadlines live with the capsule, independent of its page."""
import json
import math
import time
from datetime import datetime, timedelta
from pathlib import Path

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from config_store import _atomic
from resource_options import component_location, resource_page_active


DEFAULT_STATE = dict(
    phase='focus', status='idle', until=0., remaining=0, total=0,
    day='', water_ml=0, last_ml=0, water_at=0., water_alerted=False,
    prior_water_at=0., prior_water_alerted=False,
    stopwatch_status='idle', stopwatch_since=0., stopwatch_elapsed=0.,
    alarm_time='08:00', alarm_daily=False, alarm_at=0., alarm_due=False,
)


def state_path(config_dir):
    return Path(config_dir) / 'resource-pomodoro.json'


def read_state(path):
    state=dict(DEFAULT_STATE)
    try:
        with path.open('rb') as file:
            raw=file.read(4097)
        data=json.loads(raw) if len(raw)<=4096 else None
        if not isinstance(data,dict):
            return state
        for key,default in state.items():
            value=data.get(key)
            if type(value) is type(default):
                state[key]=value
            elif type(default) is float and type(value) is int and 0<=value<10**10:
                state[key]=float(value)
        if state['phase'] not in ('focus','rest') or state['status'] not in ('idle','running','paused','done'):
            return dict(DEFAULT_STATE)
        for key in ('until','water_at','prior_water_at','stopwatch_since','stopwatch_elapsed','alarm_at'):
            if not 0<=state[key]<10**10:
                state[key]=0.
        state['total']=min(7200,max(0,state['total']))
        state['remaining']=min(state['total'],max(0,state['remaining']))
        state['water_ml']=min(100000,max(0,state['water_ml']))
        state['last_ml']=min(1000,state['water_ml'],max(0,state['last_ml']))
        state['day']=state['day'][:10]
        if state['stopwatch_status'] not in ('idle','running','paused') or (state['stopwatch_status']=='running' and not state['stopwatch_since']):
            state.update(stopwatch_status='idle',stopwatch_since=0.,stopwatch_elapsed=0.)
        try:datetime.strptime(state['alarm_time'],'%H:%M')
        except ValueError:state.update(alarm_time='08:00',alarm_at=0.,alarm_due=False)
    except (OSError,ValueError,RecursionError):
        return dict(DEFAULT_STATE)
    return state


def duration_text(seconds):
    return f'{seconds//60:02d}:{seconds%60:02d}'


def elapsed_text(seconds):
    hours,rest=divmod(int(seconds),3600)
    return f'{hours}:{duration_text(rest)}' if hours else duration_text(rest)


def next_alarm(stamp,now):
    hour,minute=map(int,stamp.split(':'))
    local=datetime.fromtimestamp(now)
    target=local.replace(hour=hour,minute=minute,second=0,microsecond=0)
    if target.timestamp()<=now:target+=timedelta(days=1)
    return target.timestamp()


def water_amount(ml):
    return f'{ml/1000:g} L' if ml>=1000 else f'{ml} mL'


class Pomodoro(QObject):
    changed=pyqtSignal()

    def __init__(self,owner,clock=time.time):
        super().__init__(owner)
        self.owner=owner;self.clock=clock
        self.path=state_path(owner.runtime.api.CONFIG_DIR)
        self.state=read_state(self.path)
        self.error=''
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.sync)

    @property
    def cfg(self):return self.owner.cfg

    def enabled(self):
        return resource_page_active(self.cfg,'pomodoro')

    def focus(self,now=None):
        state=self.state;phase=state['phase'];status=state['status']
        now=self.clock() if now is None else now
        total=state['total'] if status!='idle' and state['total'] else self.phase_seconds(phase)
        if status=='running':
            left=min(total,max(0,math.ceil(state['until']-now)))
        elif status=='idle':left=total
        else:left=state['remaining']
        return phase,status,left,total

    def phase_seconds(self,phase):
        return 60*self.cfg['resource_focus_minutes' if phase=='focus' else 'resource_break_minutes']

    def elapsed(self):
        state=self.state
        active=max(0.,self.clock()-state['stopwatch_since']) if state['stopwatch_status']=='running' else 0.
        return state['stopwatch_elapsed']+active

    def toggle_stopwatch(self):
        if self.state['stopwatch_status']=='running':
            change=dict(stopwatch_status='paused',stopwatch_elapsed=self.elapsed(),stopwatch_since=0.)
        else:change=dict(stopwatch_status='running',stopwatch_since=self.clock())
        if self.save(change):self.sync()

    def reset_stopwatch(self):
        if self.save(dict(stopwatch_status='idle',stopwatch_elapsed=0.,stopwatch_since=0.)):self.sync()

    def arm_alarm(self,stamp,daily):
        if self.save(dict(alarm_time=stamp,alarm_daily=bool(daily),alarm_at=next_alarm(stamp,self.clock()),alarm_due=False)):
            self.sync()

    def cancel_alarm(self):
        if self.save(dict(alarm_at=0.,alarm_due=False)):self.sync()

    def dismiss_alarm(self):
        if self.save(dict(alarm_due=False)):self.sync()

    def water(self):
        return (self.cfg['resource_water_enabled'],self.state['water_ml'],self.cfg['resource_water_goal'],
                self.state['water_at'],self.state['water_alerted'])

    def badges(self):
        if not self.enabled():
            return ()
        badges=[]
        if self.cfg.get('resource_alert_alarm',True):
            if self.state['alarm_due']:badges.append(('alarm_due',self.state['alarm_time']))
            elif self.state['alarm_at']:badges.append(('alarm',self.state['alarm_time']))
        status=self.state['stopwatch_status']
        if self.cfg.get('resource_alert_stopwatch',True) and status!='idle':
            badges.append(('stopwatch' if status=='running' else 'stopwatch_paused',elapsed_text(self.elapsed())))
        if self.cfg['resource_alert_water'] and self.cfg['resource_water_enabled'] and self.state['water_alerted']:
            badges.append(('water','喝水'))
        phase,status,left,_=self.focus()
        if not self.cfg['resource_alert_focus']:return tuple(badges)
        if status=='done':badges.append((phase+'_done','完成'))
        elif status=='paused':badges.append(('paused',duration_text(left)))
        elif status=='running':badges.append((phase,duration_text(left)))
        return tuple(badges)

    def save(self,values,automatic=False):
        candidate=dict(self.state,**values)
        if candidate==self.state:
            return True
        try:
            _atomic(self.path,json.dumps(candidate,ensure_ascii=False).encode('utf-8'))
        except OSError:
            self.error='番茄钟记录保存失败，请检查数据目录。'
            if not automatic:
                self.changed.emit()
                return False
        else:self.error=''
        self.state=candidate
        return True

    def select(self,phase):
        if phase!=self.state['phase'] and self.save(dict(phase=phase,status='idle',until=0.,remaining=0,total=0)):
            self.sync()

    def toggle(self):
        self.sync()
        phase,status,left,total=self.focus()
        if status=='running':
            values=dict(status='paused',until=0.,remaining=left)
        else:
            if status!='paused':
                left=total=self.phase_seconds(phase)
            values=dict(status='running',until=self.clock()+left,total=total,remaining=0)
        if self.save(values):self.sync()

    def reset(self):
        if self.save(dict(status='idle',until=0.,remaining=0,total=0)):self.sync()

    def next_water(self):
        return self.clock()+60*self.cfg['resource_water_interval']

    def drink(self):
        self.sync()
        state=self.state
        amount=min(self.cfg['resource_water_amount'],100000-state['water_ml'])
        values=dict(day=datetime.fromtimestamp(self.clock()).date().isoformat(),water_ml=state['water_ml']+amount,
                    last_ml=amount,water_alerted=False,water_at=self.next_water() if self.cfg['resource_water_enabled'] else 0.,
                    prior_water_at=state['water_at'],prior_water_alerted=state['water_alerted'])
        if self.save(values):self.sync()

    def undo(self):
        self.sync()
        state=self.state
        if state['last_ml'] and self.save(dict(water_ml=state['water_ml']-state['last_ml'],last_ml=0,
                                               water_at=state['prior_water_at'],water_alerted=state['prior_water_alerted'],
                                               prior_water_at=0.,prior_water_alerted=False)):
            self.sync()

    def delay_water(self):
        if self.save(dict(water_at=self.next_water(),water_alerted=False)):
            self.sync()

    def sync(self):
        self.timer.stop()
        if not self.enabled():
            return
        now=self.clock();local=datetime.fromtimestamp(now);day=local.date().isoformat()
        state=dict(self.state);alerts=[]
        if state['alarm_at'] and now>=state['alarm_at']:
            alerts.append(('alarm',state['alarm_time']+' 闹钟时间到了。'))
            state.update(alarm_due=True,alarm_at=next_alarm(state['alarm_time'],now) if state['alarm_daily'] else 0.)
        if state['day']!=day and (state['day'] or self.cfg['resource_water_enabled']):
            state.update(day=day,water_ml=0,last_ml=0,water_at=0.,water_alerted=False,
                         prior_water_at=0.,prior_water_alerted=False)
        if state['status']=='running' and now>=state['until']:
            state.update(status='done',until=0.,remaining=0)
            if self.cfg['resource_alert_focus']:
                alerts.append(('focus_done','专注结束，可以休息一下。') if state['phase']=='focus'
                              else ('rest_done','休息结束，可以开始下一轮专注。'))
        water=self.cfg['resource_water_enabled']
        if not water or state['water_ml']>=self.cfg['resource_water_goal']:
            state.update(water_at=0.,water_alerted=False)
        elif not state['water_at']:
            state['water_at']=now+60*self.cfg['resource_water_interval']
        elif now>=state['water_at'] and not state['water_alerted']:
            state['water_alerted']=True
            if self.cfg['resource_alert_water']:alerts.append(('water','到喝水时间了。'))
        self.save(state,automatic=True)
        runtime=self.owner.runtime
        if alerts and not (runtime.dock.preview or runtime.game_active):
            runtime.tray.showMessage('番茄钟','\n'.join(message for _,message in alerts),runtime.tray.icon(),5000)
            for kind,_ in alerts:self.owner.play_reminder_sound(kind)
        self.changed.emit()

        deadlines=[state['alarm_at']] if state['alarm_at'] else []
        watch_running=state['stopwatch_status']=='running'
        if state['status']=='running' or watch_running:
            if state['status']=='running':deadlines.append(state['until'])
            window=self.owner.window
            compact_countdown=(self.cfg['resource_alert_focus'] or
                               'pomodoro' in self.cfg['resource_compact_metrics'] and
                               self.cfg['resource_fold']!='ball' and component_location(self.cfg,'pomodoro')=='capsule')
            live_view=(compact_countdown and state['status']=='running' or watch_running and
                       self.cfg.get('resource_alert_stopwatch',True)) if self.owner.compact else bool(window and window.page_key=='pomodoro')
            desktop=self.owner.detached('pomodoro')
            if (desktop and desktop.isVisible()) or (window and window.isVisible() and live_view):
                deadlines.append(now+1)
        if water or state['day']:
            tomorrow=(local+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
            deadlines.append(tomorrow.timestamp())
            if state['water_at'] and not state['water_alerted']:
                deadlines.append(state['water_at'])
        if deadlines:
            self.timer.start(max(1,min(86400000,math.ceil(1000*(min(deadlines)-now)))))
