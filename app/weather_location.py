"""Background Windows location on startup and after each local date change."""
import json
import subprocess
import threading
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from config_store import _atomic


_LOCATION_FAILURES = ('permission', 'timeout', 'unavailable')
_ADDRESS_VERSION = 2
_CURRENT_LOCATION = '当前位置'


def windows_position(*,refresh=False):
    from probe_lifecycle import release_native, start_native
    from resource_probes import binary
    mode = '--weather-location-refresh' if refresh else '--weather-location'
    try:
        process = start_native(
            [str(binary('DesktopResourceProbe.exe')), mode],
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
            return round(lat,3),round(lon,3)
    return None


def address_name(address):
    from resource_weather import clean_cities

    def place(value):
        return next(iter(clean_cities([value])), '')

    if not isinstance(address, dict) or address.get('lookupSource') == 'ip-geolocation':
        return _CURRENT_LOCATION
    city = place(address.get('city'))
    subdivision = place(address.get('principalSubdivision'))
    fallback = city or place(address.get('locality')) or subdivision or _CURRENT_LOCATION
    locality = address.get('localityInfo')
    administrative = locality.get('administrative') if isinstance(locality, dict) else None
    if address.get('countryCode') != 'CN' or not isinstance(administrative, list):
        return fallback

    prefecture = coded_county = boundary_county = ''
    for area in administrative:
        if not isinstance(area, dict):
            continue
        name = place(area.get('name'))
        if not name or name in ('市辖区', '县', '省直辖县级行政区划', '自治区直辖县级行政区划'):
            continue
        code = str(area.get('chinaAdminCode', ''))
        if len(code) == 6 and code.isascii() and code.isdecimal():
            if not code.endswith('00'):
                coded_county = name
            elif not code.endswith('0000'):
                prefecture = name
        elif area.get('adminLevel') == 5:
            prefecture = name
        elif area.get('adminLevel') == 6:
            boundary_county = name

    county = coded_county or boundary_county
    if not county:
        return prefecture or fallback
    parent = prefecture or city or subdivision
    if not parent or county.startswith(parent):
        return county
    if parent.endswith(county):
        return parent
    return place(f'{parent} · {county}') or county


def location_name(path,coords,lookup,*,refresh=False):
    """Reuse a district-aware label for an unchanged Windows position."""
    from resource_weather import WEATHER_ERRORS,clean_cities
    cached = _CURRENT_LOCATION
    try:
        with path.open('rb') as source:
            raw=source.read(1025)
        record=json.loads(raw) if len(raw)<=1024 else {}
        if (coordinates(record)==coords and record.get('address_version')==_ADDRESS_VERSION
                and record.get('name')!=_CURRENT_LOCATION):
            cached=clean_cities([record.get('name')],strict=True)[0]
    except (OSError,ValueError,RecursionError):
        pass
    if not refresh and cached!=_CURRENT_LOCATION:
        return cached
    lat,lon=coords
    try:
        address=lookup('https://api.bigdatacloud.net/data/reverse-geocode-client?'+
                       urlencode(dict(latitude=lat,longitude=lon,localityLanguage='zh')))
        name = address_name(address)
        return name if name!=_CURRENT_LOCATION else cached
    except WEATHER_ERRORS:
        return cached


class WeatherLocation:
    def __init__(self):
        self._lock=threading.Lock()
        self._record=None

    def resolve(self,directory,lookup,cancelled,*,refresh=False,read=None):
        path=Path(directory)/'weather-location.json'
        with self._lock:
            if cancelled():return None,'unavailable'
            previous=record=self._record
            changed=(refresh or record is None or record['day']!=date.today().isoformat())
            if changed:
                position=(read or windows_position)(refresh=refresh)
                # A request that completes after midnight also covers the new day.
                record={'day':date.today().isoformat()}
                coords=coordinates(position)
                if coords is not None:
                    record.update(status='ready',latitude=coords[0],longitude=coords[1])
                else:
                    state=position.get('status') if isinstance(position,dict) else None
                    status=state if state in _LOCATION_FAILURES else 'unavailable'
                    if (refresh and status!='permission' and previous and 'name' in previous
                            and record['day']==previous['day']):
                        record.update(previous)
                    record['status']=status
                self._record=record
            if cancelled():return None,'unavailable'
            coords=coordinates(record)
            if coords is not None and 'name' not in record:
                record['name']=location_name(path,coords,lookup,refresh=refresh)
                record['address_version']=_ADDRESS_VERSION
                changed=True
            if changed:
                try:
                    _atomic(path,json.dumps(record,ensure_ascii=False).encode('utf-8'))
                except OSError:
                    pass
            return ((record['name'],coords) if coords is not None else None),record['status']
