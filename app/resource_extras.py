"""Optional weather updates for the visible resource capsule."""
from PyQt5.QtCore import QObject,QTimer,Qt


class ResourceExtras(QObject):
    def __init__(self,service):
        super().__init__(service);self.service=service;self.closed=False;self.weather=[];self.weather_job=None
        self.weather_key=();self.location_status='disabled'
        self.weather_timer=QTimer(self);self.weather_timer.setInterval(15*60*1000);self.weather_timer.timeout.connect(self.refresh_weather)
    def sync(self):
        if self.closed:return
        if not self.service.feature_visible('weather'):self.pause();return
        cfg=self.service.cfg;cities=tuple(cfg['resource_weather_cities']);source=cfg['resource_air_source']
        location=self.service.runtime.api.CONFIG_DIR if cfg['resource_weather_location'] else None
        if cfg['resource_weather'] and (cities or location):
            from weather_connection import connection
            credentials=connection(self.service.runtime.api) if source=='qweather' else ('','')
            key=(cities,source,credentials,location)
            if key!=self.weather_key:
                self.cancel();self.weather_key=key;self.weather=[];self.location_status='unavailable' if location else 'disabled'
                self.refresh_weather()
            elif not self.weather_timer.isActive():self.refresh_weather()
            self.weather_timer.start()
        else:self.pause();self.weather_key=();self.weather=[];self.location_status='disabled'
    def located_city(self):
        return next((row['name'] for row in self.weather if row.get('located')),None)

    def city_names(self):
        located=self.located_city()
        cities=self.service.cfg['resource_weather_cities']
        return tuple(dict.fromkeys(([located] if located else [])+cities))

    def weather_alert(self):
        from resource_weather import active_weather_notice
        for row in self.weather:
            if notice:=active_weather_notice(row):
                return row['name'],notice['label']
        return None
    def cancel(self):
        job,self.weather_job=self.weather_job,None
        if job:job.requestInterruption();job.deleteLater()
    def refresh_weather(self,*,refresh_location=False):
        if self.closed or self.weather_job or not self.service.cfg['resource_weather'] or self.service.runtime.dock.preview:return
        from resource_weather import WeatherJob
        if not self.weather_key:return
        self.weather_job=WeatherJob(*self.weather_key,location_session=self.service.weather_location,
                                    refresh_location=refresh_location);job=self.weather_job
        job.ready.connect(self.receive_weather,Qt.QueuedConnection);job.finished.connect(self.finished,Qt.QueuedConnection);job.start()
    def receive_weather(self,rows):
        if self.closed or self.sender() is not self.weather_job:return
        if self.weather_job:self.location_status=self.weather_job.location_status
        import time
        from resource_weather import active_weather_notice
        old={r['name']:r for r in self.weather};updated=[]
        new_condition=False
        for row in rows:
            previous=old.get(row['name'],{})
            if row.get('error') and previous.get('temperature') is not None:
                row=dict({k:v for k,v in previous.items() if k not in ('air','air_error')},**row)
            notice=active_weather_notice(row)
            if notice and notice['label']!=(previous.get('notice') or {}).get('label'):
                new_condition=True
            cached=previous.get('air')
            if 'air' not in row and cached and time.time()-cached.get('received',0)<7200:
                row['air']=dict(cached,stale=True)
            updated.append(row)
        self.weather=updated
        self.service.display()
        if new_condition and self.service.cfg['resource_weather_alert_sound']:
            self.service.play_reminder_sound('weather')
    def finished(self):
        job=self.sender()
        if job is None or job is not self.weather_job:return
        self.weather_job=None
        job.deleteLater()
        if not self.closed:self.service.display()
    def pause(self):
        self.weather_timer.stop();self.cancel()
    def close(self):
        self.closed=True;self.pause()
        self.deleteLater()
