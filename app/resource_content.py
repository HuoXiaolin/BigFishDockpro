"""Visible-only network cards for subscribed headlines and Bing pictures."""
import time
from PyQt5.QtCore import QByteArray,QBuffer,QIODevice,QPointF,QRectF,QSize,QStandardPaths,QTimer,Qt,QUrl,pyqtSignal
from PyQt5.QtGui import QColor,QDesktopServices,QImage,QImageReader,QPainter,QPainterPath,QPen
from PyQt5.QtWidgets import QAbstractButton,QFileDialog,QHBoxLayout,QToolButton,QVBoxLayout,QWidget
from background_worker import BackgroundWorker
from content_sources import BING,download_bing_original,fetch,read_bing,read_feed,read_local_pictures
from ui_style import label
from card_design import paint_capsule_card


class ContentJob(BackgroundWorker):
    ready=pyqtSignal(object)
    def __init__(self,kind,source,index):
        super().__init__()
        self.kind,self.source,self.index=kind,source,index

    def run(self):
        if self.kind=='news':
            import xml.etree.ElementTree as xml
            rows=[];failed=0
            for url in self.source:
                if self.cancelled.is_set():return
                try:rows.extend(read_feed(fetch(url,512*1024),url))
                except (OSError,ValueError,TypeError,OverflowError,xml.ParseError):failed+=1
            rows.sort(key=lambda row:row['stamp'] or 0,reverse=True)
            unique={}
            for row in rows:unique.setdefault(row['url'],row)
            value=(list(unique.values())[:10],failed)
        elif self.kind=='local':
            paths,items=self.source
            if items is None:items=read_local_pictures(paths,self.cancelled)
            image=QImage()
            if items and not self.cancelled.is_set():
                reader=QImageReader(items[self.index]['picture']);reader.setAutoTransform(True)
                size=reader.size()
                if size.isValid() and size.width()*size.height()<=24_000_000:
                    reader.setScaledSize(size.scaled(QSize(640,420),Qt.KeepAspectRatio));image=reader.read()
            value=(items,image)
        else:
            items=self.source
            image=QImage()
            try:
                items=items or read_bing(fetch(BING+'/HPImageArchive.aspx?format=js&idx=0&n=8&mkt=zh-CN',128*1024))
                if self.cancelled.is_set():return
                if items:
                    image=self.decode(fetch(items[self.index]['picture'],512*1024))
            except (OSError,ValueError,TypeError,KeyError,IndexError):pass
            value=(items,image)
        if not self.cancelled.is_set():self.ready.emit(value)

    @staticmethod
    def decode(data):
        buffer=QBuffer();buffer.setData(QByteArray(data));buffer.open(QIODevice.ReadOnly)
        reader=QImageReader(buffer);reader.setDecideFormatFromContent(True)
        size=reader.size()
        if not size.isValid() or size.width()>1920 or size.height()>1080:return QImage()
        reader.setScaledSize(size.scaled(640,360,Qt.KeepAspectRatio))
        return reader.read()


class Picture(QWidget):
    def __init__(self,owner):
        super().__init__();self.owner=owner;self.image=QImage();self.setFixedHeight(135)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHints(QPainter.Antialiasing|QPainter.SmoothPixmapTransform)
        rect=QRectF(self.rect())
        clip=QPainterPath();clip.addRoundedRect(rect,8,8);p.setClipPath(clip)
        if self.image.isNull():
            p.fillRect(rect,QColor(self.owner.colors['hover']))
            return
        width,height=self.image.width(),self.image.height()
        ratio=min(width/rect.width(),height/rect.height()) if rect.width()>0 else 1
        crop_w,crop_h=rect.width()*ratio,rect.height()*ratio
        p.drawImage(rect,self.image,QRectF((width-crop_w)/2,(height-crop_h)/2,crop_w,crop_h))


class PictureExport(BackgroundWorker):
    ready=pyqtSignal(str,bool)

    def __init__(self,url,path,wallpaper):
        super().__init__();self.url=url;self.path=path;self.wallpaper=wallpaper

    def run(self):
        from http.client import HTTPException
        try:
            if self.url:
                if self.wallpaper:self.path.parent.mkdir(parents=True,exist_ok=True)
                if not download_bing_original(self.url,self.path,self.cancelled):return
            elif not self.path.is_file():raise FileNotFoundError(self.path)
            if self.cancelled.is_set():return
        except (OSError,ValueError,HTTPException):
            if not self.cancelled.is_set():self.ready.emit('原图下载或保存失败',False)
            return
        if self.wallpaper:
            from wallpaper_source import set_wallpaper
            try:set_wallpaper(self.path)
            except OSError:self.ready.emit('Windows 未能设置壁纸',False)
            else:self.ready.emit('已设为桌面壁纸',True)
        else:self.ready.emit('原图已保存',False)


class Headline(QAbstractButton):
    def __init__(self,owner,entry):
        super().__init__()
        self.owner,self.entry=owner,entry
        stamp=entry['stamp']
        when=time.strftime('%m/%d %H:%M',time.localtime(stamp)) if stamp is not None else ''
        self.metadata=' · '.join(value for value in (entry['source'],when) if value)
        self.setFixedHeight(39)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(entry['title'])
        self.setToolTip(entry['title'])
        self.clicked.connect(lambda:QDesktopServices.openUrl(QUrl(entry['url'])))

    def paintEvent(self,event):
        from resource_compact import text
        c=self.owner.colors
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        paint_capsule_card(p,QRectF(self.rect()),c,'lavender',self.owner.background,radius=7,
                           active=self.isDown() or self.underMouse(),focused=self.hasFocus())
        text(p,QRectF(10,3,self.width()-37,17),self.entry['title'],c['ink'],12,True)
        text(p,QRectF(10,21,self.width()-37,13),self.metadata,c['muted'],10)
        p.setPen(QPen(QColor(c['muted']),1.3,Qt.SolidLine,Qt.RoundCap))
        x,y=self.width()-16,self.height()/2
        p.drawLine(QPointF(x-2,y-3),QPointF(x+1,y))
        p.drawLine(QPointF(x+1,y),QPointF(x-2,y+3))


class ContentView(QWidget):
    def __init__(self,owner,kind):
        super().__init__()
        self.owner,self.kind=owner,kind
        self.job=None;self.source=None;self.items=[];self.index=0;self.next_fetch=0.
        self.is_local=False
        body=QVBoxLayout(self);body.setContentsMargins(0,0,0,0);body.setSpacing(4)
        head=QHBoxLayout();head.setSpacing(3)
        if kind=='picture':
            self.picture_icons={};self.icon_ink=None
            from resource_pages import MediaLabel
            self.heading=MediaLabel(1,11,True,owner=owner);self.heading.setText('每日图片')
            head.addWidget(self.heading,1)
            self.previous=self.control(head,'前一天',lambda:self.turn(-1 if self.is_local else 1),symbol='back')
            self.position=label('','muted');head.addWidget(self.position)
            self.newer=self.control(head,'后一天',lambda:self.turn(1 if self.is_local else -1),symbol='fold')
            head.addSpacing(3)
            self.reload=self.control(head,'刷新',self.refresh_now,symbol='refresh')
            self.story=self.control(head,'看故事',self.open_story,symbol='story')
            self.download=self.control(head,'下载原图',self.save_original,symbol='download')
            self.wallpaper=self.control(head,'设为壁纸',lambda:self.save_original(True),
                                        '将当前原图设为所有屏幕的 Windows 桌面壁纸',symbol='wallpaper')
        else:
            self.heading=label('新闻订阅');head.addWidget(self.heading,1)
            self.reload=self.control(head,'刷新',self.refresh_now)
        body.addLayout(head)
        self.status=label('','muted')
        if kind=='news':
            self.rows=QVBoxLayout();self.rows.setSpacing(3);body.addLayout(self.rows)
        else:
            self.setObjectName('DailyPictureContent')
            self.photo=Picture(owner);body.addWidget(self.photo)
            self.title=MediaLabel(1,12,True,owner=owner);body.addWidget(self.title);self.title.hide()
            self.credit=MediaLabel(1,10,owner=owner);body.addWidget(self.credit);self.credit.hide()
            self.status.setFixedHeight(14);self.status.setWordWrap(False);self.status.hide()
        body.addWidget(self.status)
        self.timer=QTimer(self);self.timer.setInterval(60000);self.timer.timeout.connect(self.tick)
        self.update_controls()

    def control(self,row,title,callback,description=None,*,symbol=None):
        widget=QToolButton();widget.setAccessibleName(title);widget.setToolTip(description or title)
        if symbol:
            widget.setFixedSize(22,22);widget.setIconSize(QSize(15,15));widget.setCursor(Qt.PointingHandCursor)
            self.picture_icons[widget]=symbol
        else:widget.setText(title)
        widget.clicked.connect(callback);row.addWidget(widget)
        return widget

    def update_icons(self):
        from flash_view import icon
        ink=self.owner.colors['ink']
        if ink==self.icon_ink:return
        self.icon_ink=ink
        for widget,symbol in self.picture_icons.items():widget.setIcon(icon(symbol,ink,15))

    def set_status(self,message):
        self.status.setText(message)
        if self.kind=='picture':self.status.setVisible(bool(message))

    def showEvent(self,event):
        super().showEvent(event);self.timer.start();self.refresh()

    def hideEvent(self,event):
        self.timer.stop();self.cancel()
        super().hideEvent(event)

    def cancel(self):
        if self.job is not None:
            self.job.requestInterruption();self.job.deleteLater();self.job=None

    def tick(self):
        if self.is_local:self.turn(1)
        else:self.refresh()

    def refresh(self):
        if not self.isVisible():return
        if self.kind=='picture':
            self.is_local=self.owner.cfg['daily_picture_source']=='local'
            paths=tuple(self.owner.cfg['daily_picture_local_paths']) if self.is_local else ()
            source=(self.is_local,paths)
            interval=self.owner.cfg['daily_picture_interval']*1000 if self.is_local else 60000
            if self.timer.interval()!=interval:self.timer.setInterval(interval)
            if self.source!=source:
                self.source=source;self.cancel();self.items=[];self.index=0;self.next_fetch=0.
                self.heading.setText('本地轮播' if self.is_local else '每日图片')
                self.heading.setToolTip('本地图片轮播' if self.is_local else '必应每日图片')
                self.previous.setToolTip('上一张' if self.is_local else '前一天')
                self.newer.setToolTip('下一张' if self.is_local else '后一天')
                self.set_status('');self.set_picture(QImage());self.update_controls()
            if self.is_local:
                if not paths:self.set_status('右键选择图片或文件夹')
                elif not self.job and self.next_fetch==0:self.start(renew=True)
                return
        if self.kind=='news':
            urls=tuple(self.owner.service.cfg['resource_news_feeds'])
            if self.source!=urls:
                self.source=urls;self.cancel();self.set_headlines([]);self.next_fetch=0.
            if not urls:
                self.status.setText('到资源胶囊设置「天气与内容」添加 RSS 或 Atom 订阅。')
                self.update_controls()
                return
        if not self.job and time.monotonic()>=self.next_fetch and (self.kind=='news' or self.index==0):
            self.start(renew=True)

    def refresh_now(self):
        self.next_fetch=0.
        if self.kind=='picture':
            self.index=0
            self.set_picture(QImage())
        self.refresh()

    def turn(self,step):
        target=self.index+step
        if self.is_local and len(self.items)>1:target%=len(self.items)
        if not self.job and 0<=target<len(self.items):
            if target==self.index:return
            self.index=target
            if self.is_local:self.timer.start()
            self.start()

    def open_story(self):
        if self.items and self.items[self.index]['story']:
            QDesktopServices.openUrl(QUrl(self.items[self.index]['story']))

    def save_original(self,wallpaper=False):
        from pathlib import Path
        if self.job or not self.items:return
        item=self.items[self.index];url=item.get('original')
        if not url and not (wallpaper and self.is_local):return
        name='Bing-'+item.get('date','')+'.jpg'
        runtime=self.owner.service.runtime
        if wallpaper:
            if runtime.dock.preview:return
            path=Path(item['picture']) if self.is_local else Path(runtime.api.CONFIG_DIR)/'bing-wallpapers'/name
        else:
            folder=QStandardPaths.writableLocation(QStandardPaths.PicturesLocation)
            filename,_=QFileDialog.getSaveFileName(self,'保存必应原图',str(Path(folder)/name),'JPEG 图像 (*.jpg *.jpeg)')
            if not filename:return
            path=Path(filename)
            if not path.suffix:path=path.with_suffix('.jpg')
        job=self.job=PictureExport(url,path,wallpaper)
        job.ready.connect(self.export_finished,Qt.QueuedConnection)
        job.finished.connect(self.finished,Qt.QueuedConnection)
        self.set_status('正在下载原图…');self.update_controls();job.start()

    def export_finished(self,message,wallpaper_changed):
        if self.sender() is not self.job:return
        if wallpaper_changed:
            from wallpaper_source import invalidate_source
            invalidate_source()
            self.owner.glass.clear();self.owner.update()
            self.owner.service.runtime.dock.start_backdrop()
        self.set_status(message)

    def start(self,renew=False):
        if self.owner.service.runtime.dock.preview and not self.is_local:return
        if self.is_local:
            kind='local';source=(self.source[1],None if renew else self.items)
        else:
            kind=self.kind;source=self.source if self.kind=='news' else [] if renew else self.items
        job=self.job=ContentJob(kind,source,self.index)
        job.ready.connect(self.receive,Qt.QueuedConnection)
        job.finished.connect(self.finished,Qt.QueuedConnection)
        self.set_status('正在读取…');self.update_controls()
        job.start()

    def receive(self,result):
        if self.sender() is not self.job:return
        if self.kind=='news':
            rows,failed=result;self.set_headlines(rows)
            self.status.setText(f'{failed} 个订阅暂时无法更新' if failed else '' if rows else '暂无新闻')
            self.next_fetch=time.monotonic()+900
        else:
            items,image=result
            if items or self.is_local:self.items=items
            self.set_picture(image)
            if self.is_local and not items:self.set_status('未找到可用的本地图片')
            else:self.set_status('图片暂时无法读取' if image.isNull() else '')
            self.next_fetch=time.monotonic()+(3600 if self.items else 300)
        self.update_controls()

    def finished(self):
        job=self.sender()
        if job is self.job:
            self.job=None;self.update_controls()
        job.deleteLater()

    def update_controls(self):
        self.reload.setEnabled(self.job is None and (self.kind=='picture' or bool(self.source)))
        if self.kind=='picture':
            self.previous.setEnabled(self.job is None and (len(self.items)>1 if self.is_local else self.index+1<len(self.items)))
            self.newer.setEnabled(self.job is None and (len(self.items)>1 if self.is_local else self.index>0))
            self.story.setVisible(not self.is_local);self.download.setVisible(not self.is_local)
            self.story.setEnabled(bool(self.items and self.items[self.index]['story']))
            available=self.job is None and bool(self.items and self.items[self.index].get('original'))
            self.download.setEnabled(available);self.wallpaper.setEnabled(available or self.is_local and self.job is None and bool(self.items))

    def set_headlines(self,rows):
        while self.rows.count():
            item=self.rows.takeAt(0)
            item.widget().deleteLater()
        for entry in rows:
            self.rows.addWidget(Headline(self.owner,entry))

    def set_picture(self,image):
        self.photo.image=image;self.photo.update()
        item=self.items[self.index] if self.items else {}
        date=item.get('date','')
        self.position.setText(f'{date[4:6]}/{date[6:8]}  {self.index+1}/{len(self.items)}' if date else f'{self.index+1}/{len(self.items)}' if self.items else '')
        self.title.setText(item.get('title',''));self.credit.setText(item.get('credit',''))
        self.title.setVisible(bool(self.title.text()));self.credit.setVisible(bool(self.credit.text()))
        self.title.setToolTip(self.title.text());self.credit.setToolTip(self.credit.text())
