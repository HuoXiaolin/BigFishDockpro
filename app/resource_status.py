"""Color ramps and ring dimensions shared by resource, quota and device indicators."""
import math


# Each theme uses a readable low-intensity tone and a stronger tone of the same hue.
COLOR_RAMPS = {
    'green': ((0x26764f, 0x075a37), (0xa0e9be, 0x50cb8a)),
    'yellow': ((0x886305, 0x6c4600), (0xffe4a1, 0xf5bd47)),
    'orange': ((0xa65019, 0x863305), (0xffca9d, 0xf58d49)),
    'red': ((0xb43a50, 0x8f1229), (0xffa1ac, 0xff6b7c)),
    'cyan': ((0x206b88, 0x135578), (0xa4e7f9, 0x57bee2)),
    'blue': ((0x3066a5, 0x1c4385), (0xb2cbff, 0x7d9ff7)),
    'purple': ((0x80539d, 0x65328c), (0xe2c5ff, 0xb990ed)),
    'maroon': ((0x96435f, 0x6f2046), (0xf2abc3, 0xe17da3)),
}
BATTERY_WARNING_LEVEL = 15
TRAY_RING_SIZES = (16, 20, 24, 32, 48, 64)


def ring_dimensions(diameter, count=1):
    pitch = diameter / (2 * max(1, count) + 1)
    stroke = max(1., pitch * .64)
    radius = (diameter - stroke) / 2 - .6
    return radius, stroke, pitch


def band_ink(value, soft_at, strong_at, hue, light):
    """Interpolate within a band, including bands that strengthen as the value falls."""
    amount = min(1., max(0., (value - soft_at) / (strong_at - soft_at)))
    soft, strong = COLOR_RAMPS[hue][0 if light else 1]
    color = 0
    for shift in (16, 8, 0):
        first = (soft >> shift) & 255
        last = (strong >> shift) & 255
        color = (color << 8) | round(first + (last - first) * amount)
    return f'#{color:06x}'


def low_battery_ink(level, light):
    return band_ink(level, BATTERY_WARNING_LEVEL, 0, 'red', light)


def threshold(value,maximum=100,light=False):
    if (not isinstance(value, (int, float)) or not math.isfinite(value)
            or not isinstance(maximum, (int, float)) or not math.isfinite(maximum) or maximum <= 0):
        return None
    ratio = value / maximum
    if ratio >= .8:
        return band_ink(ratio, .8, 1, 'red', light)
    if ratio >= .6:
        return band_ink(ratio, .6, .8, 'yellow', light)
    return band_ink(ratio, 0, .6, 'green', light)


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
