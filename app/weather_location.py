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
_CACHE_FILE = 'weather-location.json'


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
    if address.get('countryCode') != 'CN':
        return fallback

    municipality = subdivision if subdivision.endswith('市') else ''
    if not isinstance(administrative, list):
        return city or municipality or fallback
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
            elif name.endswith('市'):
                municipality = name
        elif area.get('adminLevel') == 4 and name.endswith('市'):
            municipality = name
        elif area.get('adminLevel') == 5:
            prefecture = name
        elif area.get('adminLevel') == 6:
            boundary_county = name

    county = coded_county or boundary_county
    if not county:
        return prefecture or municipality or fallback
    parent = prefecture or municipality or city or subdivision
    if not parent or parent == county:
        return county
    if county.startswith(parent):
        county = county[len(parent):]
    elif parent.endswith(county):
        parent = parent[:-len(county)]
    return place(f'{parent} · {county}') or county


def load_location(directory):
    """Load the last usable position, including caches from earlier versions."""
    from resource_weather import clean_cities
    try:
        with (Path(directory) / _CACHE_FILE).open('rb') as source:
            raw=source.read(1025)
        record=json.loads(raw) if len(raw)<=1024 else {}
        if coordinates(record) is not None:
            record['name']=next(iter(clean_cities([record.get('name')])),_CURRENT_LOCATION)
            return record
    except (OSError,ValueError,RecursionError):
        pass
    return None


def location_name(previous,coords,lookup,*,refresh=False):
    """Reuse a district-aware label for an unchanged Windows position."""
    from resource_weather import WEATHER_ERRORS
    cached = _CURRENT_LOCATION
    if coordinates(previous)==coords and previous.get('address_version')==_ADDRESS_VERSION:
        cached=previous['name']
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
    def __init__(self,log=None):
        self._lock=threading.Lock()
        self._log=log
        self._directory=None
        self._attempt_day=None
        self._status='unavailable'
        self._record=None

    def resolve(self,directory,lookup,cancelled,*,refresh=False,read=None):
        directory=Path(directory)
        with self._lock:
            if cancelled():return None,'unavailable'
            if directory!=self._directory:
                self._directory=directory
                self._record=load_location(directory)
                self._attempt_day=None
                self._status='unavailable'
            if refresh or self._attempt_day!=date.today():
                position=(read or windows_position)(refresh=refresh)
                if cancelled():return None,'unavailable'
                coords=coordinates(position)
                if coords is None:
                    state=position.get('status') if isinstance(position,dict) else None
                    self._status=state if state in _LOCATION_FAILURES else 'unavailable'
                else:
                    name=location_name(self._record,coords,lookup,refresh=refresh)
                    if cancelled():return None,'unavailable'
                    self._status='ready'
                    self._record=dict(day=date.today().isoformat(),status='ready',name=name,
                                      latitude=coords[0],longitude=coords[1],address_version=_ADDRESS_VERSION)
                    try:
                        _atomic(directory/_CACHE_FILE,json.dumps(self._record,ensure_ascii=False).encode('utf-8'))
                    except OSError:
                        pass
                # A request that completes after midnight covers the new day.
                self._attempt_day=date.today()
                if self._log:
                    trigger='手动' if refresh else '自动'
                    self._log(f'天气定位（{trigger}） {self._status}')
            record=self._record
            return ((record['name'],coordinates(record)) if record else None),self._status
