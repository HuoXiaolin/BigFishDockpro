"""Display order shared by compact capsule settings and the painted row."""
from typing import NamedTuple

from resource_options import (COMPACT_CONTENT, COMPACT_ITEMS, COMPACT_ROUTINES, COMPACT_STATUS, COMPACT_ZONES as ZONES,
                              DEVICE_ALERTS, PINNABLE, RESOURCE_READINGS, almanac_categories, component_location)


def device_key(kind):
    # The numeric device chip replaces the ordinary readout when both are on.
    return kind if kind in ('volume','brightness') else 'device_' + kind


BADGE_KEYS = {
    'focus':'focus', 'rest':'focus', 'focus_done':'focus', 'rest_done':'focus', 'paused':'focus',
    'alarm_due':'alarm', 'stopwatch_paused':'stopwatch', 'weather_notice':'weather',
    'quota_notice':'quota',
}


def badge_key(kind, active):
    if kind == 'almanac':
        return 'alert_almanac'
    name = BADGE_KEYS.get(kind, kind)
    if active:
        return 'alert_' + name
    return 'pomodoro' if name == 'focus' else name


ALERT_NAMES = {
    'alert_mail_code':'邮箱验证码', 'alert_agenda':'日程到时提醒', 'alert_battery':'电脑低电量提醒',
    'alert_alarm':'闹钟', 'alert_stopwatch':'正计时', 'alert_water':'喝水提醒',
    'alert_focus':'番茄钟倒计时与完成提醒', 'alert_weather':'天气提醒', 'alert_almanac':'节气与节日提醒',
    'alert_mail_new':'新邮件提醒', 'alert_quota':'AI 额度提醒',
}
NAMES = {'face':'胶囊表情', 'resources':'资源轮换', **{k:v for k,v in PINNABLE.items() if k not in RESOURCE_READINGS}, **{key:COMPACT_ITEMS[key] for key in COMPACT_STATUS},
         'mail':'邮箱图标', **{device_key(key):title for key,title in DEVICE_ALERTS.items()},
         **ALERT_NAMES, 'runner':'跑步小动物', 'clock':'日期与时间'}


class PageTurns(NamedTuple):
    shared: int = 0
    left: int = 0
    center: int = 0
    right: int = 0

    def advance(self, step, zones):
        return self._replace(shared=self.shared+step, **{zone:getattr(self,zone)+step for zone in zones})


def automatic_step(layout, turns, enabled):
    bands = layout['bands']
    index = turns.shared % len(bands)
    current = bands[index]
    # When several zones must share a narrow row, keep a paused visible zone on screen.
    if all(zone in enabled for zone in current):
        for step in range(1,len(bands)):
            if all(zone in enabled for zone in bands[(index+step) % len(bands)]):
                return step
    if any(layout['zone_periods'][zone]>1 for zone in current if zone in enabled):
        return len(bands)
    return 0


def clock_turn(layout, turns):
    return getattr(turns,layout.get('clock_zone','right')) // len(layout['bands']) // layout.get('clock_stride',1)


def has_component_order(cfg):
    return bool(cfg.get('resource_compact_zones')) or any(key not in PINNABLE and key!='resources' for key in cfg['resource_compact_order'])


def group_resource_order(cfg, order, zones):
    """In an older layout, inherit the position of the first enabled hardware readout."""
    if not any(k in RESOURCE_READINGS for k in (*order,*zones)):
        return list(order), dict(zones)
    candidates = [k for k in dict.fromkeys([*order,*zones]) if k in RESOURCE_READINGS]
    selected = cfg.get('resource_compact_metrics', ())
    if not isinstance(selected,(list,tuple)):
        selected = ()
    anchor = next((k for k in candidates if k in selected and cfg.get('resource_'+k)), candidates[0])
    if 'resources' in order:
        anchor = 'resources'
    merged = ['resources' if k == anchor else k for k in order if k == anchor or k not in RESOURCE_READINGS]
    assigned = {k:v for k,v in zones.items() if k not in RESOURCE_READINGS}
    if anchor in zones:
        assigned.setdefault('resources', zones[anchor])
    return merged, assigned


def _saved_order(cfg):
    saved, _ = group_resource_order(cfg, cfg.get('resource_compact_order', ()), cfg.get('resource_compact_zones', {}))
    if any(key not in PINNABLE and key!='resources' for key in saved):
        # Add future items before a clock that was deliberately left at the end.
        result = list(dict.fromkeys([*saved, *NAMES]))
        if saved[-1] == 'clock':
            result.remove('clock')
            result.append('clock')
        return result
    # Older profiles ordered readouts only. Preserve their pinned/readout priority.
    ordinary = ('resources','traffic',*COMPACT_CONTENT)
    readings = ['resources' if key in RESOURCE_READINGS else key for key in (*saved, *cfg['resource_compact_pinned'], *ordinary) if key not in COMPACT_ROUTINES]
    routines = list(dict.fromkeys([*(key for key in saved if key in COMPACT_ROUTINES),*COMPACT_ROUTINES]))
    status = [key for key in COMPACT_STATUS if key not in ('volume','brightness') or not cfg['resource_alert_'+key]]
    return list(dict.fromkeys(['face', *readings, 'alert_almanac', *reversed(routines), *status, 'mail',
                               *(device_key(kind) for kind in DEVICE_ALERTS), *reversed(ALERT_NAMES), *NAMES]))


def item_zones(cfg, order):
    _, assigned = group_resource_order(cfg, cfg.get('resource_compact_order', ()), cfg.get('resource_compact_zones', {}))
    # An existing clock deliberately moved into the row keeps its old neighbours.
    return {key:assigned.get(key, 'right' if key=='clock' and key==order[-1] else 'left') for key in order}


def display_order(cfg):
    order = _saved_order(cfg)
    zones = item_zones(cfg, order)
    return [key for zone in ZONES for key in order if zones[key]==zone]


def assign_visible(cfg, groups):
    order = _saved_order(cfg)
    zones = item_zones(cfg, order)
    for zone, visible in groups.items():
        zones.update(dict.fromkeys(visible, zone))
    result = []
    for zone, visible in groups.items():
        result.extend(merge_visible([key for key in order if zones[key]==zone], visible))
    # Explicitly store the clock's side, even when all visible items are on the left.
    return result, {key:zone for key,zone in zones.items() if zone!='left' or key=='clock'}


def configured_items(cfg):
    """Use preferences, not live sensor values, pending messages or hardware presence."""
    selected = set(cfg['resource_compact_metrics'])
    enabled = set()
    if component_location(cfg,'resources') == 'capsule':
        if any(key in selected and cfg.get('resource_'+key) for key in RESOURCE_READINGS):
            enabled.add('resources')
        if cfg['resource_system_status']:
            enabled.update(selected.intersection(('battery','connection','volume','brightness')))
        if 'bluetooth' in selected and (cfg['resource_bluetooth'] or cfg.get('resource_peripheral_profiles')):
            enabled.add('bluetooth')
    for key, option in COMPACT_CONTENT.items():
        if cfg[option] and cfg['resource_'+key] and component_location(cfg,key) == 'capsule':
            enabled.add(key)
    for key, page in (('traffic','traffic'), ('agenda','agenda'), ('water','pomodoro'), ('pomodoro','pomodoro')):
        if key in selected and cfg['resource_'+page] and component_location(cfg,page) == 'capsule':
            enabled.add(key)
    for key, option in (('face','resource_face'), ('runner','resource_runner_enabled'), ('clock','resource_clock'),
                        ('alert_battery','resource_alert_battery')):
        if cfg[option]:
            enabled.add(key)
    if almanac_categories(cfg):
        enabled.add('alert_almanac')
    if cfg['resource_mail']:
        for key, option in (('mail','resource_mail_icon'), ('alert_mail_new','resource_mail_notifications'),
                            ('alert_mail_code','resource_alert_mail_code')):
            if cfg[option]:
                enabled.add(key)
    if cfg['resource_pomodoro']:
        for kind in ('focus','alarm','stopwatch','water'):
            if cfg['resource_alert_'+kind] and (kind != 'water' or cfg['resource_water_enabled']):
                enabled.add('alert_'+kind)
    for page in ('agenda','weather'):
        if cfg['resource_'+page] and cfg['resource_alert_'+page]:
            enabled.add('alert_'+page)
    if (cfg['resource_ai'] or cfg['resource_ai_tray']) and cfg['resource_quota_alert']:
        enabled.add('alert_quota')
    enabled.update(device_key(key) for key in DEVICE_ALERTS if cfg['resource_alert_'+key])
    return {key:NAMES[key] for key in display_order(cfg) if key in enabled}


def merge_visible(order, visible):
    """Keep disabled items in their saved slots when reordering a filtered list."""
    keys = set(visible)
    replacement = iter(visible)
    return [next(replacement) if key in keys else key for key in order]
