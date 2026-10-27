"""A low-frequency desktop clock with independent appearance and live preview."""
import ctypes
import datetime
import os
from types import SimpleNamespace
from PyQt5.QtCore import Qt, QTimer, QRectF, QPointF, QVariantAnimation, QEasingCurve
from PyQt5.QtGui import QPainter, QPainterPath, QColor, QPen, QFont
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
        self.setAttribute(Qt.WA_TranslucentBackground); self.setWindowTitle('桌面'+self.component_name+' · 大肥鱼Dock')
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
            self.flip_button=button('↔',self.flip);self.flip_button.setParent(self);self.flip_button.setFixedSize(24,24);self.flip_button.setToolTip('点击翻面：时钟 / 月历');self.flip_button.show()
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
            self.flip_button.move(self.width()-34,10)
            self.flip_button.setStyleSheet('QPushButton {background:rgba(140,170,195,26);color:#41617a;border:0;border-radius:6px;padding:0;font-size:17px;} QPushButton:hover {background:rgba(140,170,195,65);}')

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
        draw_clock(painter,QRectF(self.rect()).adjusted(1,1,-1,-1),self.dock,self.option('appearance'),'calendar_card' if face else self.option('style'),self.backdrop)

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
    painter.save();painter.setRenderHint(QPainter.Antialiasing);painter.setRenderHint(QPainter.TextAntialiasing)
    w,h=rect.width(),rect.height();painter.translate(rect.left(),rect.top());rect=QRectF(0,0,w,h)
    material=options['material'];colors=material_palette(tint_palette(dock.base_theme_colors(options['theme']),options['color']),material)
    strength=options['highlight']/45
    colors['border'].setAlpha(min(255,round(colors['border'].alpha()*strength)));colors['spec']=min(255,round(colors['spec']*strength))
    stops=[(position,min(255,round(alpha*strength))) for position,alpha in dock.merged_grad_stops(colors)]
    shape=QPainterPath();shape.addRoundedRect(rect,min(20,h*.14),min(20,h*.14))
    surface=SimpleNamespace(cfg={'glass':material not in ('clear','solid'),'clear_background':material=='clear' and options['opacity']==0 and options['highlight']==0,'dock_material':material},backdrop=backdrop,spec_x=w*.54,spec_alpha=.24)
    paint_liquid_glass(surface,painter,shape,rect,rect,colors,round(options['opacity']*2.55),stops)
    from card_design import paint_design
    paint_design(painter,rect,dock.cfg,options.get('design'),clear=surface.cfg['clear_background'])
    painter.setClipPath(shape)
    light=colors.get('light',True);ink=QColor(options['text_color'] or '#ffffff')
    design=options.get('design','follow');design=dock.cfg.get('card_design','aurora') if design=='follow' else design
    background=clock_background_color(backdrop,colors,material)
    if design in ('gradient','paper','minimal') and not surface.cfg['clear_background']:background=QColor('#f4f7fa')
    # On a transparent clock, never turn explicitly white text grey from an
    # estimated or unrelated background; capture may be unavailable on Windows.
    transparent_white=material=='clear' and min(ink.red(),ink.green(),ink.blue())>=245
    if background is not None and not transparent_white:ink=contrast_ink(ink,background)
    muted=QColor(ink);muted.setAlpha(255);accent=QColor(options['color'] or ('#3686bc' if light else '#8fc8ee'))
    if light and accent.lightness()>140:accent=accent.darker(185)
    elif not light and accent.lightness()<120:accent=accent.lighter(165)
    if background is not None:accent=contrast_ink(accent,background,minimum=4.5)
    now=datetime.datetime.now();time_text,period=format_clock_time(now,options['hour_format'])
    hour=int(time_text[:2])
    date_text='%d月%d日  周%s'%(now.month,now.day,'一二三四五六日'[now.weekday()]);scale=options['font_scale']/100
    margin=max(9,w*.075)
    def font(size,weight=QFont.Normal):
        f=QFont(options['font']);f.setPixelSize(max(8,round(size)));f.setWeight(QFont.Bold if weight>=QFont.DemiBold and size>=21 else max(QFont.DemiBold,weight))
        if size>=21:f.setLetterSpacing(QFont.PercentageSpacing,102);f.setStretch(105)
        f.setStyleStrategy(QFont.PreferAntialias);return f
    def text(box,value,size,color,weight=QFont.Normal,align=Qt.AlignLeft|Qt.AlignVCenter,fit=True):
        f=font(size,weight)
        if any('\u3400'<=character<='\u9fff' for character in value):
            f.setFamily('Microsoft YaHei UI');f.setStretch(100);f.setLetterSpacing(QFont.PercentageSpacing,100);f.setWeight(max(QFont.DemiBold,weight))
        if fit:
            while f.pixelSize()>8 and QFontMetricsF(f).horizontalAdvance(value)>box.width():f.setPixelSize(f.pixelSize()-1)
        painter.setFont(f)
        # Soft offset shadows improve contrast without outlining each glyph.
        from PyQt5.QtGui import QLinearGradient
        metrics=QFontMetricsF(f);width=metrics.horizontalAdvance(value)
        x=box.x()+(box.width()-width)/2 if align & Qt.AlignHCenter else box.right()-width if align & Qt.AlignRight else box.x()
        baseline=box.y()+(box.height()-metrics.height())/2+metrics.ascent()
        glyph=QPainterPath();glyph.addText(QPointF(x,baseline),f,value)
        shadows=((1.0,28),) if style in ('calendar','orbit','month','calendar_card') and f.pixelSize()>=24 else (() if style in ('calendar','orbit','month','calendar_card') else ((3.0,18),(2.0,35),(1.0,75)))
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
    from clock_faces import draw_face
    if draw_face(style,painter,w,h,now,options,ink,muted,accent,text,time_text,period):pass
    elif style=='analog':
        horizontal=w>=h*1.35;cx=w*.31 if horizontal else w*.5;cy=h*.5;radius=min(h*.34,w*(.25 if horizontal else .34))
        halo=QColor(accent);halo.setAlpha(28);painter.setBrush(halo);painter.setPen(Qt.NoPen);painter.drawEllipse(QPointF(cx,cy),radius*1.16,radius*1.16)
        # A transparent white clock uses white dial marks and hands for clarity.
        dial_accent=QColor(ink) if transparent_white else QColor(accent)
        edge=QColor('#172d43' if ink.lightness()>205 else '#ffffff');edge.setAlpha(140)
        painter.setBrush(Qt.NoBrush);painter.setPen(QPen(edge,max(2,h*.015)));painter.drawEllipse(QPointF(cx,cy),radius,radius)
        rim=QColor(ink);rim.setAlpha(220);painter.setPen(QPen(rim,max(1,h*.008)));painter.drawEllipse(QPointF(cx,cy),radius,radius)
        for i in range(12):
            angle=i*math.pi/6;mark=QColor(dial_accent if i%3==0 else ink);mark.setAlpha(220 if i%3==0 else 100)
            mark.setAlpha(240);start=QPointF(cx+math.sin(angle)*radius*.80,cy-math.cos(angle)*radius*.80);end=QPointF(cx+math.sin(angle)*radius*.91,cy-math.cos(angle)*radius*.91)
            stroke=max(1.4,h*.013) if i%3==0 else max(1.1,h*.008)
            painter.setPen(QPen(edge,stroke+1.5,Qt.SolidLine,Qt.RoundCap));painter.drawLine(start,end)
            painter.setPen(QPen(mark,stroke,Qt.SolidLine,Qt.RoundCap));painter.drawLine(start,end)
        for angle,length,width,color in [((now.hour%12+now.minute/60)*math.pi/6,.48,.027,ink),(now.minute*math.pi/30,.70,.015,dial_accent)]:
            start=QPointF(cx,cy);end=QPointF(cx+math.sin(angle)*radius*length,cy-math.cos(angle)*radius*length);stroke=max(2,h*width)
            painter.setPen(QPen(edge,stroke+2,Qt.SolidLine,Qt.RoundCap));painter.drawLine(start,end)
            painter.setPen(QPen(color,stroke,Qt.SolidLine,Qt.RoundCap));painter.drawLine(start,end)
        painter.setPen(Qt.NoPen);painter.setBrush(dial_accent);painter.drawEllipse(QPointF(cx,cy),max(2.5,h*.021),max(2.5,h*.021))
        if horizontal:
            x=w*.59;span=w-x-margin
            if period:text(QRectF(x,h*.22,span,h*.14),period,h*.075,muted,QFont.DemiBold)
            text(QRectF(x,h*(.39 if period else .32),span,h*.26),time_text,h*.21*scale,ink,QFont.DemiBold)
            if options['show_date']:text(QRectF(x,h*.66,span,h*.14),date_text,h*.09,muted)
        elif period:
            text(QRectF(margin,h*.04,w-2*margin,h*.14),period,h*.075,muted,QFont.DemiBold,Qt.AlignCenter)
    elif style=='stacked':
        x=margin;usable=w-2*margin
        if period:text(QRectF(x,h*.10,usable,h*.13),period,h*.075,muted,QFont.DemiBold)
        left='%02d'%hour;right='%02d'%now.minute
        text(QRectF(x,h*.27,usable*.46,h*.45),left,h*.42*scale,ink,QFont.DemiBold,Qt.AlignLeft|Qt.AlignVCenter)
        line=QColor(accent);line.setAlpha(150);painter.setPen(QPen(line,max(1,h*.01)));painter.drawLine(QPointF(w*.50,h*.35),QPointF(w*.50,h*.67))
        text(QRectF(w*.54,h*.27,usable*.44,h*.45),right,h*.42*scale,ink,QFont.DemiBold,Qt.AlignLeft|Qt.AlignVCenter)
        if options['show_date']:text(QRectF(x,h*.78,usable,h*.12),date_text,h*.09,muted)
    else:
        if period:text(QRectF(margin,h*.12,w-2*margin,h*.16),period,h*.075,muted,QFont.DemiBold)
        top=.30 if period else (.23 if options['show_date'] else .27)
        text(QRectF(margin,h*top,w-2*margin,h*.42),time_text,h*.43*scale,ink,QFont.DemiBold)
        if options['show_date']:
            line=QColor(ink);line.setAlpha(45);painter.setPen(QPen(line,1));painter.drawLine(QPointF(margin,h*.74),QPointF(w-margin,h*.74))
            text(QRectF(margin,h*.77,w-2*margin,h*.13),date_text,h*.09,muted)
    painter.restore()


class ClockPreview(QWidget):
    def __init__(self,dialog):
        super().__init__();self.dialog=dialog;self.setMinimumSize(200,105);self.setMaximumHeight(180)
    def paintEvent(self,event):
        painter=QPainter(self);clock=self.dialog.clock;ratio=clock.width()/max(1,clock.height())
        height=min(self.height()-4,(self.width()-4)/ratio);width=height*ratio
        target=QRectF((self.width()-width)/2,(self.height()-height)/2,width,height)
        options=self.dialog.values()
        if clock.kind=='calendar':options=dict(options,_calendar_year=clock.view_year,_calendar_month=clock.view_month)
        draw_clock(painter,target,clock.dock,options,'calendar_card' if clock.kind=='calendar' else self.dialog.fields['style'].currentData())


class ClockOptions(QDialog):
    def __init__(self,clock):
        super().__init__(clock,Qt.Window|Qt.FramelessWindowHint|Qt.WindowMinimizeButtonHint)
        self.clock=clock;self.fields={};self.loading=True;self.calendar=clock.kind=='calendar'
        component=clock.component_name
        self.setWindowTitle(component+'设置 · 大肥鱼Dock');self.resize(640,760);self.setMinimumSize(460,480)
        body=QVBoxLayout(self);body.addWidget(SettingsHeader(self,component+'设置'))
        body.addWidget(label(component+'外观独立保存，调整后可在下方预览。','muted'))
        self.preview=ClockPreview(self);body.addWidget(self.preview)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.NoFrame);content=QWidget();form=QFormLayout(content);form.setVerticalSpacing(9);scroll.setWidget(content);body.addWidget(scroll,1)
        self.preset=ModernComboBox();self.preset.addItem('自定义 / 保留当前设置')
        for name,_ in PRESETS:self.preset.addItem(name)
        form.addRow('外观预设',self.preset)
        def choice(key,title,items):
            field=ModernComboBox();field.setAccessibleName(title)
            for name,value in items:field.addItem(name,value)
            self.fields[key]=field;form.addRow(title,field)
        def number(key,title,low,high):
            field=ModernSpinBox();field.setRange(low,high);field.setAccessibleName(title);self.fields[key]=field;form.addRow(title,field)
        if not self.calendar:choice('style','样式',STYLES)
        from card_design import DESIGNS
        choice('design','卡片风格',[('跟随软件卡片风格','follow')]+DESIGNS)
        choice('font','字体',FONTS);choice('text_effect','字体效果',[('通透玻璃','glass'),('清晰','clear')]);number('font_scale','主要文字字号（%）',60,150)
        if not self.calendar:choice('hour_format','时间格式',[('24 小时','24'),('12 小时','12')])
        self.show_date=ModernCheckBox('数字与表盘显示附加日期')
        if not self.calendar:form.addRow('',self.show_date)
        choice('material','背景材质',MATERIALS);choice('theme','明暗模式',COLOR_MODES)
        def color(key,title):
            field=QLineEdit();field.setAccessibleName(title);field.setPlaceholderText('默认色 / #RRGGBB');self.fields[key]=field
            box=QVBoxLayout();row=QHBoxLayout();row.addWidget(field,1);row.addWidget(button('选择',lambda:self.choose_color(field)));box.addLayout(row)
            if key=='color':box.addWidget(ThemeSwatches(field))
            form.addRow(title,box)
        color('color','背景主题色');color('text_color','文字颜色')
        self.fields['text_color'].setPlaceholderText('默认白色 / #RRGGBB')
        self.fields['text_color'].setToolTip('透明背景的白色文字保持白色；其他颜色在可判断背景时会自动调整显示亮度。')
        number('opacity','背景不透明度（%）',0,100);number('blur','背景模糊强度',2,30);number('highlight','背景高光（%）',0,100)
        self.status=label('保存后立即应用，关闭窗口不会保存未提交的修改。','muted');body.addWidget(self.status)
        actions=QHBoxLayout();actions.addStretch();actions.addWidget(button('关闭',self.reject));actions.addWidget(button('保存设置',self.commit,'primary'));body.addLayout(actions)
        saved=clock.option('appearance')
        for key,field in self.fields.items():
            value=clock.option('style') if key=='style' else saved[key]
            if isinstance(field,QComboBox):field.setCurrentIndex(max(0,field.findData(value)))
            elif isinstance(field,QLineEdit):field.setText(value)
            else:field.setValue(value)
        self.show_date.setChecked(saved['show_date']);self.loading=False
        for field in self.fields.values():
            signal=field.currentIndexChanged if isinstance(field,QComboBox) else field.textChanged if isinstance(field,QLineEdit) else field.valueChanged
            signal.connect(self.changed)
        self.show_date.toggled.connect(self.changed);self.preset.currentIndexChanged.connect(self.apply_preset)
        compact_dialog(self)
        from settings_layout import fit_auxiliary_dialog
        fit_auxiliary_dialog(self,clock.dock.cfg)
    def values(self):
        values={}
        for key,field in self.fields.items():
            if key=='style':continue
            values[key]=field.currentData() if isinstance(field,QComboBox) else field.text().strip() if isinstance(field,QLineEdit) else field.value()
        values['show_date']=self.show_date.isChecked();values['typography_version']=2;return normalize_appearance(values)
    def changed(self,*args):
        if self.loading:return
        self.preset.blockSignals(True);self.preset.setCurrentIndex(0);self.preset.blockSignals(False);self.preview.update()
    def apply_preset(self,index):
        if index<=0:return
        self.loading=True
        for key,value in PRESETS[index-1][1].items():
            field=self.fields[key]
            if isinstance(field,QComboBox):field.setCurrentIndex(field.findData(value))
            elif isinstance(field,QLineEdit):field.setText(value)
            else:field.setValue(value)
        self.loading=False;self.preview.update()
    def choose_color(self,field):
        color=QColorDialog.getColor(QColor(field.text() or '#b8d9ef'),self,'选择颜色')
        if color.isValid():field.setText(color.name())
    def commit(self):
        import re
        for key in ('color','text_color'):
            value=self.fields[key].text().strip()
            if value and not re.fullmatch(r'#[0-9a-fA-F]{6}',value):self.status.setText('颜色请使用 #RRGGBB，或留空使用默认色。');return False
        if self.clock.save(clock_appearance=self.values(),**({} if self.calendar else {'clock_style':self.fields['style'].currentData()})):
            self.clock.sync();self.status.setText('已保存并应用'+self.clock.component_name+'外观。');return True
        self.status.setText('保存失败，原设置保持不变，可重试。');return False
