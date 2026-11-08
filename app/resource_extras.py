"""Optional weather updates for the visible resource capsule."""
from PyQt5.QtCore import QObject,QTimer,Qt


class ResourceExtras(QObject):
    def __init__(self,service):
        super().__init__(service);self.service=service;self.closed=False;self.weather=[];self.weather_job=None
        self.weather_key=()
        self.weather_timer=QTimer(self);self.weather_timer.setInterval(15*60*1000);self.weather_timer.timeout.connect(self.refresh_weather)
    def sync(self):
        if self.closed:return
        if not self.service.window or not self.service.window.isVisible():self.pause();return
        cfg=self.service.cfg;cities=tuple(cfg['resource_weather_cities']);source=cfg['resource_air_source']
        if cfg['resource_weather'] and cities:
            from weather_connection import connection
            credentials=connection(self.service.runtime.api) if source=='qweather' else ('','')
            key=(cities,source,credentials)
            if key!=self.weather_key:
                self.cancel();self.weather_key=key;self.weather=[]
                self.refresh_weather()
            elif not self.weather_timer.isActive():self.refresh_weather()
            self.weather_timer.start()
        else:self.pause();self.weather_key=();self.weather=[]
    def cancel(self):
        job,self.weather_job=self.weather_job,None
        if job:job.requestInterruption();job.deleteLater()
    def refresh_weather(self):
        if self.closed or self.weather_job or not self.service.cfg['resource_weather'] or self.service.runtime.dock.preview:return
        from resource_weather import WeatherJob
        if not self.weather_key:return
        self.weather_job=WeatherJob(*self.weather_key);job=self.weather_job
        job.ready.connect(self.receive_weather,Qt.QueuedConnection);job.finished.connect(self.finished,Qt.QueuedConnection);job.start()
    def receive_weather(self,rows):
        if self.closed or self.sender() is not self.weather_job:return
        import time
        old={r['name']:r for r in self.weather};updated=[]
        for row in rows:
            previous=old.get(row['name'],{})
            if row.get('error') and previous.get('temperature') is not None:
                row=dict({k:v for k,v in previous.items() if k not in ('air','air_error')},**row)
            cached=previous.get('air')
            if 'air' not in row and cached and time.time()-cached.get('received',0)<7200:
                row['air']=dict(cached,stale=True)
            updated.append(row)
        self.weather=updated
        self.service.display()
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
