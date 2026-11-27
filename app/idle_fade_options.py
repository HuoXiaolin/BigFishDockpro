"""Saved desktop fade choices. Only floating component windows have a key."""

MODES = (('custom', '自定义'), ('on', '全部开启'), ('off', '全部关闭'))
SINGLE_FIELDS = {key: prefix + '_idle_fade' for key, prefix in (
    ('dock', 'dock'), ('resource', 'resource'), ('flash', 'flash'), ('clock', 'clock'),
    ('calendar', 'calendar'), ('picture', 'daily_picture'), ('spectrum', 'spectrum'),
    ('watermark', 'watermark'),
)}
POLICY_FIELDS = {*SINGLE_FIELDS.values(), 'component_idle_fade', 'desktop_idle_fade_mode', 'desktop_idle_fade_amount'}
LABEL = '空闲 6 秒后淡化'
HINT = '全局淡化设为「自定义」时，单独控制此桌面组件。'


def instance_key(key):
    if not isinstance(key, str) or len(key) > 120:
        return False
    group, _, identity = key.partition(':')
    return bool(identity) and group in ('panel', 'note', 'custom', 'resource')


def normalize(cfg):
    # The previous master switch was on by default, before individual choices existed.
    cfg.pop('desktop_idle_fade', None)
    if cfg['desktop_idle_fade_mode'] not in tuple(key for key, _ in MODES):
        cfg['desktop_idle_fade_mode'] = 'custom'
    for field in SINGLE_FIELDS.values():
        cfg[field] = cfg.get(field) is True
    saved = cfg.get('component_idle_fade')
    cfg['component_idle_fade'] = ({k: True for k, v in saved.items() if instance_key(k) and v is True}
                                  if isinstance(saved, dict) else {})


def individual(cfg, key):
    field = SINGLE_FIELDS.get(key)
    return cfg.get(field, False) if field else cfg.get('component_idle_fade', {}).get(key, False)


def enabled(cfg, key):
    if key not in SINGLE_FIELDS and not instance_key(key):
        return False
    mode = cfg['desktop_idle_fade_mode']
    return individual(cfg, key) if mode == 'custom' else mode == 'on'


def selection_changes(cfg, choices):
    changes = {}
    instances = dict(cfg['component_idle_fade'])
    for key, value in choices.items():
        if key in SINGLE_FIELDS:
            changes[SINGLE_FIELDS[key]] = value
        elif instance_key(key):
            if value:
                instances[key] = True
            else:
                instances.pop(key, None)
    if instances != cfg['component_idle_fade']:
        changes['component_idle_fade'] = instances
    return changes
