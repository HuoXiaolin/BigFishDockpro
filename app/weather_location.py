"""Background Windows location on startup and after each local date change."""
import json
import subprocess
import threading
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from config_store import _atomic


_LOCATION_FAILURES = ('permission', 'timeout', 'unavailable')


def windows_position():
    from probe_lifecycle import release_native, start_native
    from resource_probes import binary
    try:
        process = start_native(
            [str(binary('DesktopResourceProbe.exe')), '--weather-location'],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except OSError:
        return None
    if process is None:
        return None
    try:
        raw, _ = process.communicate(timeout=15)
        if not process.returncode and len(raw)<=1024:
            return json.loads(raw.decode('utf-8-sig'))
    except subprocess.TimeoutExpired:
        try:
            process.kill()
            process.communicate()
        except OSError:
            pass
        return {'status': 'timeout'}
    except (ValueError, OSError):
        pass
    finally:
        release_native(process)
    return None


def coordinates(row):
    if isinstance(row,dict):
        lat,lon=row.get('latitude'),row.get('longitude')
        if (type(lat) in (int,float) and type(lon) in (int,float) and
                -90<=lat<=90 and -180<=lon<=180):
            return round(lat,2),round(lon,2)
    return None


def city_name(path,coords,lookup):
    """Reuse the resolved city when a new Windows fix has the same coordinates."""
    from resource_weather import WEATHER_ERRORS,clean_cities
    try:
        with path.open('rb') as source:
            raw=source.read(1025)
        record=json.loads(raw) if len(raw)<=1024 else {}
        if coordinates(record)==coords and record.get('name')!='当前位置':
            return clean_cities([record.get('name')],strict=True)[0]
    except (OSError,ValueError,RecursionError):
        pass
    lat,lon=coords
    try:
        address=lookup('https://api.bigdatacloud.net/data/reverse-geocode-client?'+
                       urlencode(dict(latitude=lat,longitude=lon,localityLanguage='zh')))
        city=address.get('city') or address.get('locality') or address.get('principalSubdivision')
        return clean_cities([city],strict=True)[0]
    except WEATHER_ERRORS:
        return '当前位置'


class WeatherLocation:
    def __init__(self):
        self._lock=threading.Lock()
        self._record=None

    def resolve(self,directory,lookup,cancelled,*,retry=False,read=windows_position):
        path=Path(directory)/'weather-location.json'
        with self._lock:
            if cancelled():return None,'unavailable'
            record=self._record
            changed=(record is None or record['day']!=date.today().isoformat()
                     or (retry and record['status']!='ready'))
            if changed:
                position=read()
                # A request that completes after midnight also covers the new day.
                record={'day':date.today().isoformat()}
                coords=coordinates(position)
                if coords is not None:
                    record.update(status='ready',latitude=coords[0],longitude=coords[1])
                else:
                    state=position.get('status') if isinstance(position,dict) else None
                    record['status']=state if state in _LOCATION_FAILURES else 'unavailable'
                self._record=record
            if cancelled():return None,'unavailable'
            coords=coordinates(record)
            if coords is not None and 'name' not in record:
                record['name']=city_name(path,coords,lookup)
                changed=True
            if changed:
                try:
                    _atomic(path,json.dumps(record,ensure_ascii=False).encode('utf-8'))
                except OSError:
                    pass
            return ((record['name'],coords) if coords is not None else None),record['status']
