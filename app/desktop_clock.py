"""A low-frequency desktop clock with independent appearance and live preview."""
import ctypes
import datetime
import os
from types import SimpleNamespace
from PyQt5.QtCore import Qt, QTimer, QRectF, QPointF, QSize, QVariantAnimation, QEasingCurve
from PyQt5.QtGui import QPainter, QPainterPath, QColor, QPen, QFont, QPixmap, QIcon
from PyQt5.QtWidgets import (QWidget, QSizeGrip, QApplication, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QScrollArea, QLineEdit, QColorDialog, QComboBox)
from ui_style import (SettingsHeader, ModernComboBox, ModernSpinBox, ModernCheckBox, ThemeSwatches, button, label, compact_dialog)
from clock_appearance import STYLES, FONTS, PRESETS, normalize as normalize_appearance
from appearance_presets import MATERIALS, COLOR_MODES
from screen_layout import capture, project, screen_records, valid_record
from liquid_glass import paint_liquid_glass, tint_palette, material_palette, material_blur


class DesktopClock(QWidget):
    def __init__(self, runtime, kind="clock"):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint)
        self.runtime, self.dock = runtime, runtime.dock
        self.kind=kind;self.component_name="日历" if kind=="calendar" else "时钟"
        self.minimum=(260,230) if kind=="calendar" else (160,100)
        self.backdrop = None; self.drag = None; self.loading = True; self.closed = False
        self.setAttribute(Qt.WA_ShowWithoutActivating);self.setAttribute(Qt.WA_TranslucentBackground); self.setWindowTitle('桌面'+self.component_name+' · 大肥鱼Dock')
        self.setMinimumSize(*self.minimum)
        from ui_style import SubtleSizeGrip
        self.grip = SubtleSizeGrip(self,lambda:self.dock.base_theme_colors(self.option('appearance')['theme']).get('light',True))
        self.grip.setFixedSize(18,18)
        self.tick = QTimer(self); self.tick.setSingleShot(True); self.tick.timeout.connect(self.update_time)
        self.geometry_timer = QTimer(self); self.geometry_timer.setSingleShot(True); self.geometry_timer.setInterval(300); self.geometry_timer.timeout.connect(self.save_geometry)
        self.refresh_timer = QTimer(self); self.refresh_timer.setSingleShot(True); self.refresh_timer.setInterval(200); self.refresh_timer.timeout.connect(self.capture_backdrop)
        self.reposition(); self.loading = False; self.apply_lock()
        if self.kind=='clock':
            self.flipped=self.dock.cfg.get('clock_flipped',False);self.flip_progress=None
            self.flip_button=button('↔',self.flip);self.flip_button.setParent(self);self.flip_button.setFixedSize(12,12);self.flip_button.setToolTip('点击翻面：时钟 / 月历');self.flip_button.show()
            self.flip_animation=QVariantAnimation(self);self.flip_animation.setDuration(240);self.flip_animation.setStartValue(0.0);self.flip_animation.setEndValue(1.0);self.flip_animation.setEasingCurve(QEasingCurve.InOutCubic)
            self.flip_animation.valueChanged.connect(self.advance_flip);self.flip_animation.finished.connect(self.finish_flip);self.position_flip()


    def option(self,name):return self.dock.cfg[self.kind+'_'+name]

    def save(self, **values):
        if self.kind!='clock':values={self.kind+key[5:] if key.startswith('clock_') else key:value for key,value in values.items()}
        candidate = dict(self.dock.cfg, **values)
        if self.runtime.api.save_config(candidate) is False:
            self.runtime.api.log('桌面时钟设置保存失败。'); return False
        self.dock.cfg.update(values); return True

    def sync(self):
        if self.closed: return
        if self.kind=='clock' and hasattr(self,'flipped') and self.flip_progress is None:self.flipped=self.dock.cfg.get('clock_flipped',False)
        if getattr(self,'_applied_lock',None)!=self.option('locked'):self.apply_lock()
        visible = self.option('enabled') and not self.runtime.game_active
        if visible:
            if not self.isVisible(): self.show()
            self.update_time(); self.refresh_timer.start()
        else:
            self.tick.stop(); self.refresh_timer.stop(); self.backdrop = None; self.hide()

    def set_enabled(self, enabled):
        if self.save(clock_enabled=bool(enabled)): self.sync()

    def set_style(self, style):
        if self.save(clock_style=style,clock_flipped=False):
            self.flipped=False;self.update()

    def apply_lock(self):
        locked=self.option('locked')
        self.setMinimumSize(*self.minimum);self.setMaximumSize(16777215,16777215)
        if locked:self.setFixedSize(self.size())
        self.grip.setVisible(not locked);self._applied_lock=locked

    def set_locked(self, locked):
        locked=bool(locked);values={'clock_locked':locked}
        layout=getattr(self.runtime,'layout',None)
        if locked and not (layout and (layout.pending or layout.applying)):
            record=capture(list(self.geometry().getRect()),screen_records(),density=self.dock.cfg.get('card_scale',70)/100)
            if record:values['clock_layout']=record
        if not self.save(**values):return False
        self.drag=None;self.geometry_timer.stop();self.apply_lock();return True

    def update_time(self):
        if not self.isVisible() or self.closed: return
        self.update()
        now = datetime.datetime.now()
        self.tick.start(max(50, 60000 - now.second * 1000 - now.microsecond // 1000))

    def reposition(self):
        screens = screen_records()
        if not screens: return
        record = valid_record(self.option('layout'))
        if not record:
            x,y,w,h = screens[0]['area']
            initial=[x+w-370,y+220,330,300] if self.kind=='calendar' else [x+w-330,y+40,290,160]
            record=capture(initial,screens,density=self.dock.cfg.get('card_scale',70)/100)
        bounds = project(record,screens,minimum=self.minimum,density=self.dock.cfg.get('card_scale',70)/100)
        if bounds:
            was_loading=self.loading; self.loading=True
            self.setMinimumSize(*self.minimum);self.setMaximumSize(16777215,16777215);self.setGeometry(*bounds)
            self.loading=was_loading;self.apply_lock()

    def save_geometry(self):
        layout = getattr(self.runtime,'layout',None)
        if self.loading or self.closed or (layout and (layout.pending or layout.applying)): return
        value = capture(list(self.geometry().getRect()),screen_records(),density=self.dock.cfg.get('card_scale',70)/100)
        if value: self.save(clock_layout=value)

    def capture_backdrop(self):
        self.backdrop = None
        cfg=self.option('appearance')
        if self.isVisible() and not self.runtime.lite and not self.dock.preview and (cfg['material'] not in ('clear','solid') or cfg['text_effect']=='glass'):
            from glass_capture import capture_behind, surface_windows
            image=capture_behind(self,surface_windows(self.dock))
            if image is not None:
                ratio=image.devicePixelRatio(); divisor=material_blur(cfg['blur'],cfg['material'])
                self.backdrop=image.scaled(max(1,image.width()//divisor),max(1,image.height()//divisor),Qt.IgnoreAspectRatio,Qt.SmoothTransformation).scaled(image.size(),Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
                self.backdrop.setDevicePixelRatio(ratio)
        self.update()

    def layer(self):
        if self.dock.preview or os.environ.get('FISHDOCK_TEST_DESKTOP'): return
        from ctypes import wintypes
        user=ctypes.windll.user32; user.GetShellWindow.restype=wintypes.HWND; owner=user.GetShellWindow()
        if owner:
            user.SetWindowLongPtrW.argtypes=[wintypes.HWND,ctypes.c_int,ctypes.c_ssize_t]
            user.SetWindowLongPtrW(int(self.winId()),-8,int(owner))
            user.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
            user.SetWindowPos(int(self.winId()),1,0,0,0,0,0x13)

    def showEvent(self,event):
        super().showEvent(event); self.layer(); self.refresh_timer.start()
    def hideEvent(self,event):
        self.tick.stop(); self.refresh_timer.stop(); super().hideEvent(event)
    def moveEvent(self,event):
        super().moveEvent(event)
        if not self.loading: self.geometry_timer.start(); self.refresh_timer.start()
    def resizeEvent(self,event):
        super().resizeEvent(event); self.grip.move(self.width()-20,self.height()-20)
        self.position_flip()
        if not self.loading: self.geometry_timer.start(); self.refresh_timer.start()
    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton and not self.option('locked'): self.drag=event.globalPos()-self.pos(); event.accept()
    def mouseMoveEvent(self,event):
        if self.drag is not None: self.move(event.globalPos()-self.drag); event.accept()
    def mouseReleaseEvent(self,event):
        if self.drag is not None: self.drag=None; self.save_geometry(); event.accept()
    def open_settings(self):
        from usage_stats import record
        record(self.dock,'clock_settings')
        dialog=ClockOptions(self);dialog.exec_();dialog.deleteLater()
    def build_menu(self):
        from ui_style import AlignedMenu
        menu=AlignedMenu(self)
        menu.addAction('时钟设置…').triggered.connect(self.open_settings)
        menu.addAction('翻到时钟' if self.flipped else '翻到月历').triggered.connect(self.flip)
        styles=menu.addMenu('时钟样式')
        for title,style in STYLES:
            action=styles.addAction(title);action.setCheckable(True);action.setChecked(self.option('style')==style)
            action.triggered.connect(lambda checked=False,s=style:self.set_style(s))
        menu.addSeparator()
        locked=menu.addAction('锁定位置与大小');locked.setCheckable(True);locked.setChecked(self.option('locked'))
        locked.triggered.connect(self.set_locked)
        menu.addAction('隐藏时钟').triggered.connect(lambda:self.set_enabled(False))
        return menu
    def contextMenuEvent(self,event):
        menu=self.build_menu();menu.exec_(event.globalPos());menu.deleteLater()

    def position_flip(self):
        if hasattr(self,'flip_button'):
            self.grip.move(self.width()-20,self.height()-20)
            self.flip_button.setFixedSize(20,20)
            self.flip_button.setText('');self.flip_button.setIconSize(QSize(12,12))
            ratio=max(2.0,self.devicePixelRatioF())
            if getattr(self,'_flip_icon_ratio',None)!=ratio:
                pixmap=QPixmap(round(12*ratio),round(12*ratio));pixmap.setDevicePixelRatio(ratio);pixmap.fill(Qt.transparent)
                painter=QPainter(pixmap);painter.scale(2,2);painter.setRenderHint(QPainter.Antialiasing);painter.setPen(QPen(QColor('#41617a'),.7,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
                painter.drawLine(QPointF(.6,3),QPointF(5.4,3))
                for x,direction in ((.6,1),(5.4,-1)):
                    painter.drawLine(QPointF(x+1.4*direction,1.6),QPointF(x,3));painter.drawLine(QPointF(x,3),QPointF(x+1.4*direction,4.4))
                painter.end();self.flip_button.setIcon(QIcon(pixmap));self._flip_icon_ratio=ratio

            self.flip_button.move(self.width()-26,14)
            self.flip_button.setStyleSheet('QPushButton {background:transparent;color:#41617a;border:0;border-radius:6px;padding:0;font-size:15px;min-width:0;min-height:0;max-width:12px;max-height:12px;} QPushButton:hover {background:transparent;}')

    def flip(self):
        if self.kind!='clock' or self.flip_progress is not None:return
        self._flip_from=self.flipped;self._flip_to=not self.flipped;self.flip_progress=0;self.flip_animation.start()

    def advance_flip(self,value):self.flip_progress=float(value);self.update()
    def finish_flip(self):
        self.flipped=self._flip_to if self.save(clock_flipped=self._flip_to) else self._flip_from
        self.flip_progress=None;self.update()

    def paintEvent(self,event):
        import math
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        face=getattr(self,'flipped',False)
        if getattr(self,'flip_progress',None) is not None:
            face=self._flip_to if self.flip_progress>=.5 else self._flip_from
            painter.translate(self.width()/2,0);painter.scale(max(.015,abs(math.cos(math.pi*self.flip_progress))),1);painter.translate(-self.width()/2,0)
        draw_clock(painter,QRectF(self.rect()).adjusted(1,1,-1,-1),self.dock,dict(self.option('appearance'),_header_controls=self.kind=='clock'),'calendar_card' if face else self.option('style'),self.backdrop)

    def dispose(self):
        if self.closed:return
        if hasattr(self,'flip_animation'):self.flip_animation.stop()
        if self.geometry_timer.isActive(): self.geometry_timer.stop(); self.save_geometry()
        self.closed=True; self.tick.stop(); self.refresh_timer.stop(); self.backdrop=None; self.close(); self.deleteLater()


def format_clock_time(now,hour_format):
    hour=now.hour if hour_format=='24' else (now.hour%12 or 12)
    return '%02d:%02d'%(hour,now.minute),('' if hour_format=='24' else ('上午' if now.hour<12 else '下午'))



def contrast_ink(color,background,minimum=7.0):
    """Keep a selected hue where possible, shifting it only for low contrast."""
    def luminance(c):
        def linear(v):return v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4
        return sum(weight*linear(value) for weight,value in zip((.2126,.7152,.0722),(c.redF(),c.greenF(),c.blueF())))
    def ratio(a,b):
        left,right=sorted((luminance(a),luminance(b)));return (right+.05)/(left+.05)
    color=QColor(color);background=QColor(background)
    if ratio(color,background)>=minimum:return color
    goal=QColor('#ffffff') if ratio(QColor('#ffffff'),background)>=ratio(QColor('#101820'),background) else QColor('#101820')
    for step in range(1,21):
        weight=step/20
        adjusted=QColor(*(round(a*(1-weight)+b*weight) for a,b in zip((color.red(),color.green(),color.blue()),(goal.red(),goal.green(),goal.blue()))))
        if ratio(adjusted,background)>=minimum:return adjusted
    return goal


def clock_background_color(backdrop,colors,material):
    if material=='clear' and (backdrop is None or backdrop.isNull()):return None
    if backdrop is None or backdrop.isNull() or material=='solid':return QColor(colors['tint'])
    sample=backdrop.toImage().scaled(6,6,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
    pixels=[sample.pixelColor(x,y) for y in range(sample.height()) for x in range(sample.width())]
    if not pixels:return QColor(colors['tint'])
    return QColor(*(round(sum(getattr(c,channel)() for c in pixels)/len(pixels)) for channel in ('red','green','blue')))


def draw_clock(painter,rect,dock,options,style,backdrop=None):
    """Draw responsive clock content for both the desktop widget and settings preview."""
    import math
    from PyQt5.QtGui import QFontMetricsF
    options=dict(options,**normalize_appearance(options))
    painter.save();painter.setRenderHint(QPainter.Antialiasing);painter.setRenderHint(QPainter.TextAntialiasing)
    w,h=rect.width(),rect.height();painter.translate(rect.left(),rect.top());rect=QRectF(0,0,w,h)
    material=options['material'];colors=material_palette(tint_palette(dock.base_theme_colors(options['theme']),options['color']),material)
    strength=options['highlight']/45
    colors['border'].setAlpha(min(255,round(colors['border'].alpha()*strength)));colors['spec']=min(255,round(colors['spec']*strength))
    stops=[(position,min(255,round(alpha*strength))) for position,alpha in dock.merged_grad_stops(colors)]
    shape=QPainterPath();shape.addRoundedRect(rect,min(options['corner_radius'],h*.24),min(options['corner_radius'],h*.24))
    surface=SimpleNamespace(cfg={'glass':material not in ('clear','solid'),'clear_background':material=='clear' and options['opacity']==0 and options['highlight']==0,'dock_material':material},backdrop=backdrop,spec_x=w*.54,spec_alpha=.24)
    paint_liquid_glass(surface,painter,shape,rect,rect,colors,round(options['opacity']*2.55),stops)
    from card_design import paint_design
    paint_design(painter,rect,dock.cfg,options.get('design'),clear=surface.cfg['clear_background'],corner_radius=min(options['corner_radius'],h*.24),body_top=rect.bottom(),header_separator=False)
    painter.setClipPath(shape)
    light=colors.get('light',True);ink=QColor(options['text_color'] or ('#ffffff' if material=='clear' or not light else '#19364d'))
    design=options.get('design','follow');design=dock.cfg.get('card_design','aurora') if design=='follow' else design
    background=clock_background_color(backdrop,colors,material)
    if design in ('gradient','paper','minimal') and not surface.cfg['clear_background']:background=QColor('#f4f7fa')
    # On a transparent clock, never turn explicitly white text grey from an
    # estimated or unrelated background; capture may be unavailable on Windows.
    transparent_white=material=='clear' and min(ink.red(),ink.green(),ink.blue())>=245
    if options['auto_contrast'] and background is not None and not transparent_white:ink=contrast_ink(ink,background)
    muted=QColor(ink);muted.setAlpha(225)
    if options['accent_color']:accent=QColor(options['accent_color'])
    elif transparent_white:accent=QColor('#88e4f2')
    else:
        hue=QColor(options['color'] or '#62acd4').hslHueF();accent=QColor.fromHslF(hue if hue>=0 else .55,.62,.39 if light else .74)
    if options['auto_contrast'] and background is not None and not transparent_white:accent=contrast_ink(accent,background,minimum=3.0)
    now=options.get('_now') or datetime.datetime.now();time_text,period=format_clock_time(now,options['hour_format'])
    hour=int(time_text[:2])
    date_text='%d月%d日  周%s'%(now.month,now.day,'一二三四五六日'[now.weekday()]);scale=options['font_scale']/100
    margin=max(9,w*.075)
    def font(size,weight=QFont.Normal):
        f=QFont(options['font']);f.setPixelSize(max(8,round(size)));f.setWeight(options['font_weight'] if size>=21 else weight)
        if size>=21:f.setLetterSpacing(QFont.PercentageSpacing,options['letter_spacing']);f.setStretch(100)
        f.setStyleStrategy(QFont.PreferAntialias);return f
    def text(box,value,size,color,weight=QFont.Normal,align=Qt.AlignLeft|Qt.AlignVCenter,fit=True):
        f=font(size,weight)
        if any('\u3400'<=character<='\u9fff' for character in value) or (size<21 and not (style in ('month','calendar_card') and value.isdigit())):
            f.setFamily(options['date_font']);f.setPixelSize(max(8,round(f.pixelSize()*options['date_scale']/100)));f.setStretch(100);f.setLetterSpacing(QFont.PercentageSpacing,100);f.setWeight(weight)
        if fit:
            while f.pixelSize()>8 and (QFontMetricsF(f).horizontalAdvance(value)>box.width() or QFontMetricsF(f).height()>box.height()):f.setPixelSize(f.pixelSize()-1)
        painter.setFont(f)
        # Soft offset shadows improve contrast without outlining each glyph.
        from PyQt5.QtGui import QLinearGradient
        metrics=QFontMetricsF(f);width=metrics.horizontalAdvance(value)
        x=box.x()+(box.width()-width)/2 if align & Qt.AlignHCenter else box.right()-width if align & Qt.AlignRight else box.x()
        baseline=box.y()+(box.height()-metrics.height())/2+metrics.ascent()
        glyph=QPainterPath();glyph.addText(QPointF(x,baseline),f,value)
        shadows=((1.0,25),) if options['shadow']=='soft' and f.pixelSize()>=20 else ()
        color=QColor(color);color.setAlpha(round(color.alpha()*options['text_opacity']/100))
        for offset,opacity in shadows:
            shadow=QColor('#10253a');shadow.setAlpha(opacity)
            painter.save();painter.translate(0,offset);painter.fillPath(glyph,shadow);painter.restore()
        if options['text_effect']=='clear' or f.pixelSize()<18:
            painter.fillPath(glyph,color);return
        # Background sampling and the glass tint remain clipped to the glyph.
        painter.save();painter.setClipPath(glyph,Qt.IntersectClip)
        if backdrop is not None and not backdrop.isNull():
            painter.drawPixmap(QRectF(0,0,w,h),backdrop,QRectF(0,0,backdrop.width(),backdrop.height()))
        bounds=glyph.boundingRect();wash=QLinearGradient(0,bounds.top(),0,bounds.bottom())
        upper=QColor(color);upper.setAlpha(color.alpha())
        lower=QColor(color);lower.setAlpha(round(color.alpha()*.96))
        wash.setColorAt(0,upper);wash.setColorAt(1,lower);painter.fillRect(bounds,wash);painter.restore()
    from clock_design import draw
    draw(style,painter,w,h,now,options,ink,muted,accent,text,time_text,period)
    painter.restore()


from clock_options import ClockOptions,ClockPreview
