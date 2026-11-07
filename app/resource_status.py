"""One threshold scale for desktop, compact readings and taskbar."""
import math


def threshold(value,maximum=100,light=False):
    if not isinstance(value,(int,float)) or not math.isfinite(value) or maximum<=0:return None
    ratio=max(0,value)/maximum
    index=2 if ratio>=.8 else 1 if ratio>=.6 else 0
    return (('#087443','#986200','#c12c39') if light else ('#73e6a0','#ffd16f','#ff8589'))[index]


def metric_number(service,key):
    value=service.latest.get(key)
    if key=='memory':return value[0] if value is not None else None
    from resource_options import SENSOR_UNITS
    if key in SENSOR_UNITS:
        reading=service.sensors.values.get(key) if service.sensors else None
        return reading.get('value') if reading else None
    return value if isinstance(value,(int,float)) else None


def metric_ink(service,key,light,fallback):
    if not service.cfg.get('resource_threshold',True):return fallback
    maximum=service.cfg.get('resource_limits',{}).get(key,default_limit(key))
    return threshold(metric_number(service,key),maximum,light) or fallback


def default_limit(key):
    return 100 if key in ('cpu','gpu','memory','gpu_memory') or key.endswith('_temp') else 0
