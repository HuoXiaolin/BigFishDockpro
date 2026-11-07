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
        cfg=self.service.cfg;cities=tuple(cfg['resource_weather_cities'])
        if cfg['resource_weather'] and cities:
            if cities!=self.weather_key:
                self.cancel();self.weather_key=cities;self.weather=[]
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
        self.weather_job=WeatherJob(self.service.cfg['resource_weather_cities']);job=self.weather_job
        job.ready.connect(self.receive_weather,Qt.QueuedConnection);job.finished.connect(self.finished,Qt.QueuedConnection);job.start()
    def receive_weather(self,rows):
        if self.closed or self.sender() is not self.weather_job:return
        old={r['name']:r for r in self.weather}
        self.weather=[dict(old[r['name']],error=r['error']) if r.get('error') and r['name'] in old else r for r in rows]
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
