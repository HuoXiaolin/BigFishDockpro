"""A low-frequency desktop clock with independent appearance and live preview."""
import ctypes
import datetime
import os
from types import SimpleNamespace
from PyQt5.QtCore import Qt, QTimer, QRect, QRectF, QPointF, QSize, QVariantAnimation, QEasingCurve
from PyQt5.QtGui import QPainter, QPainterPath, QColor, QPen, QFont, QPixmap, QIcon
from PyQt5.QtWidgets import (QWidget, QSizeGrip, QApplication, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QScrollArea, QLineEdit, QColorDialog, QComboBox)
from ui_style import (SettingsHeader, ModernComboBox, ModernSpinBox, ModernCheckBox, ThemeSwatches, button, label, compact_dialog)
from clock_appearance import STYLES, FONTS, PRESETS, theme_family, normalize as normalize_appearance
from appearance_presets import LIGHT_GLASS_INK, MATERIALS, COLOR_MODES, THEME_ACCENTS, material_design
from screen_layout import capture, project, screen_records, valid_record
from liquid_glass import paint_liquid_glass, tint_palette, material_palette, material_blur
from window_edges import edges_at, paint_edge_targets, resize_cursor, resized_rect


class DesktopClock(QWidget):
    def __init__(self, runtime, kind="clock"):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint)
        self.runtime, self.dock = runtime, runtime.dock
        self.kind=kind;self.component_name="日历" if kind=="calendar" else "时钟"
        self.setProperty('clickThroughKey',kind)
        self.minimum=(260,230) if kind=="calendar" else (160,100)
        self.backdrop = None; self.drag = None; self.loading = True; self.closed = False
        self.setAttribute(Qt.WA_ShowWithoutActivating);self.setAttribute(Qt.WA_TranslucentBackground); self.setWindowTitle('桌面'+self.component_name+' · 大肥鱼Dock')
        self.setMinimumSize(*self.minimum)
        self.setAccessibleDescription('拖动卡片移动，拖动边缘或四角调整大小')
        self.tick = QTimer(self); self.tick.setSingleShot(True); self.tick.timeout.connect(self.update_time)
        self.geometry_timer = QTimer(self); self.geometry_timer.setSingleShot(True); self.geometry_timer.setInterval(300); self.geometry_timer.timeout.connect(self.save_geometry)
        self.refresh_timer = QTimer(self); self.refresh_timer.setSingleShot(True); self.refresh_timer.setInterval(200); self.refresh_timer.timeout.connect(self.capture_backdrop)
        self.reposition(); self.loading = False; self.apply_lock()
        if self.kind=='clock':
            self.flipped=self.dock.cfg.get('clock_flipped',False);self.flip_progress=None
            self.flip_button=button('',self.flip);self.flip_button.setParent(self);self.flip_button.setFixedSize(12,12);self.flip_button.setIconSize(QSize(12,12));self.flip_button.setToolTip('点击翻面：时钟 / 月历');self.flip_button.show()
            self.flip_button.setStyleSheet('QPushButton {background:transparent;border:0;padding:0;min-width:0;min-height:0;max-width:12px;max-height:12px;} QPushButton:hover {background:transparent;}')
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
        from resource_options import component_location
        routed=component_location(self.dock.cfg,self.kind)=='capsule'
        host=self.runtime.resources.hosted_component(self.kind) if routed else None
        if self.parentWidget() is not host:
            self.geometry_timer.stop();self.refresh_timer.stop()
            self.drag=None
            self.loading=True
            self.setParent(host,Qt.Widget if host else Qt.Tool|Qt.FramelessWindowHint)
            if host:
                self.setAttribute(Qt.WA_TransparentForMouseEvents,False)
                host.layout().addWidget(self)
            else:self.reposition()
            self.apply_lock()
            self.loading=False
        if self.kind=='clock' and hasattr(self,'flipped') and self.flip_progress is None:self.flipped=self.dock.cfg.get('clock_flipped',False)
        if getattr(self,'_applied_lock',None)!=self.option('locked'):self.apply_lock()
        visible = self.option('enabled') and not self.runtime.game_active and (not routed or host is not None)
        if visible:
            if not self.isVisible(): self.show()
            self.update_time()
            if not host:self.refresh_timer.start()
        else:
            self.tick.stop(); self.refresh_timer.stop(); self.backdrop = None; self.hide()

    def set_enabled(self, enabled):
        if self.save(clock_enabled=bool(enabled)):
            self.sync();self.runtime.resources.components_changed()

    def set_style(self, style):
        if self.save(clock_style=style,clock_flipped=False):
            self.flipped=False;self.update()

    def apply_lock(self):
        locked=self.option('locked')
        movable=self.can_drag()
        self.setMouseTracking(movable)
        self.setCursor(Qt.SizeAllCursor if movable else Qt.ArrowCursor)
        if not movable:self.drag=None
        if self.parentWidget() is not None:
            self.setMinimumSize(1,1);self.setMaximumSize(16777215,16777215)
            self.setFixedHeight(240 if self.kind=='calendar' else 170)
        else:
            self.setMinimumSize(*self.minimum);self.setMaximumSize(16777215,16777215)
            if locked:self.setFixedSize(self.size())
        self._applied_lock=locked
        self.update()

    def can_drag(self):
        return self.parentWidget() is None and not self.option('locked')

    def set_locked(self, locked):
        if self.parentWidget() is not None:return False
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
        seconds=self.kind=='clock' and self.option('style')=='digital' and not getattr(self,'flipped',False)
        interval=1000 if seconds else 60000-now.second*1000
        self.tick.start(max(30,interval-now.microsecond//1000))

    def reposition(self):
        if self.parentWidget() is not None:return
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
            self.loading=was_loading;self.apply_lock();self._applied_geometry=self.geometry().getRect()

    def save_geometry(self,persist=True):
        layout = getattr(self.runtime,'layout',None)
        if self.loading or self.closed or self.parentWidget() is not None or (layout and (layout.pending or layout.applying)): return
        rect=self.geometry().getRect()
        if self.option('layout') and rect==getattr(self,'_applied_geometry',None):return
        value = capture(list(rect),screen_records(),density=self.dock.cfg.get('card_scale',70)/100)
        if value:
            if not persist:self.dock.cfg[self.kind+'_layout']=value
            elif self.save(clock_layout=value):self._applied_geometry=rect
            else:return False

    def capture_backdrop(self):
        if self.parentWidget() is not None:return
        cfg=self.option('appearance')
        from glass_capture import backdrop_key
        key=backdrop_key(self,cfg['blur'],cfg['material'],cfg['text_effect'],cfg['auto_contrast']) if not self.dock.preview else None
        if key is not None and key==getattr(self,'_backdrop_key',None) and self.backdrop is not None:return
        if self.isVisible() and not self.dock.preview and (cfg['material'] not in ('clear','solid') or cfg['text_effect']=='glass' or (cfg['material']=='clear' and cfg['auto_contrast'])):
            from glass_capture import capture_behind, surface_windows
            image=capture_behind(self,surface_windows(self.dock))
            if image is not None:
                from glass_capture import smooth_backdrop
                if cfg['material']=='clear':
                    # Clear text needs a luminance sample, not a full wallpaper copy.
                    self.backdrop=image if cfg['text_effect']=='glass' else image.scaled(96,64,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
                else:self.backdrop=smooth_backdrop(image,material_blur(cfg['blur'],cfg['material']))
                self._backdrop_key=key
        elif cfg['material'] in ('clear','solid') and cfg['text_effect']!='glass':self.backdrop=None
        self.update()

    def layer(self):
        if self.parentWidget() is not None or self.dock.preview or os.environ.get('FISHDOCK_TEST_DESKTOP'): return
        from ctypes import wintypes
        user=ctypes.windll.user32; user.GetShellWindow.restype=wintypes.HWND; owner=user.GetShellWindow()
        if owner:
            user.SetWindowLongPtrW.argtypes=[wintypes.HWND,ctypes.c_int,ctypes.c_ssize_t]
            user.SetWindowLongPtrW(int(self.winId()),-8,int(owner))
            user.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
            user.SetWindowPos(int(self.winId()),1,0,0,0,0,0x13)

    def showEvent(self,event):
        super().showEvent(event)
        if self.parentWidget() is None:self.layer();self.refresh_timer.start()
    def hideEvent(self,event):
        self.tick.stop(); self.refresh_timer.stop();self.backdrop=None
        self.drag=None
        from clock_legibility import clear_cache
        clear_cache()
        super().hideEvent(event)
    def moveEvent(self,event):
        super().moveEvent(event)
        if not self.loading and self.parentWidget() is None and self.drag is None: self.geometry_timer.start(); self.refresh_timer.start()
    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.place_controls()
        if not self.loading and self.parentWidget() is None and self.drag is None: self.geometry_timer.start(); self.refresh_timer.start()
    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton and self.can_drag():
            self.geometry_timer.stop();self.refresh_timer.stop()
            self.drag=QRect(self.geometry()),event.globalPos(),edges_at(self.rect(),event.pos())
            event.accept()
        else:super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if self.drag is None:
            if self.can_drag():self.setCursor(resize_cursor(edges_at(self.rect(),event.pos())))
            return
        original,pointer,edges=self.drag
        delta=event.globalPos()-pointer
        if edges:self.setGeometry(resized_rect(original,edges,delta,self.minimum))
        else:self.move(original.topLeft()+delta)
        event.accept()
    def mouseReleaseEvent(self,event):
        if self.drag is None or event.button()!=Qt.LeftButton:
            super().mouseReleaseEvent(event)
            return
        self.mouseMoveEvent(event)
        original,_,edges=self.drag
        self.drag=None
        if self.geometry()!=original:
            if not edges:
                from card_snap import finish_drag
                finish_drag(self,event.globalPos())
            if self.save_geometry() is False:self.setGeometry(original)
        self.geometry_timer.stop();self.refresh_timer.start()
        self.setCursor(resize_cursor(edges_at(self.rect(),self.mapFromGlobal(event.globalPos()))))
        event.accept()
    def open_settings(self):
        from usage_stats import record
        record(self.dock,'clock_settings')
        dialog=ClockOptions(self);dialog.exec_();dialog.deleteLater()
    def open_progress(self):
        from clock_progress import ClockProgressDialog
        from settings_effects import save_changes
        from ui_style import exec_dialog

        def apply(progress):
            appearance=dict(self.option('appearance'),progress=progress)
            return save_changes(self.runtime.tray,self.runtime.api,dict(
                clock_appearance=appearance,clock_style='calendar' if self.option('style')=='calendar' else 'orbit',
                clock_enabled=True,clock_flipped=False))

        exec_dialog(ClockProgressDialog(self.dock,self.option('appearance')['progress'],apply))

    def build_menu(self):
        from ui_style import AlignedMenu
        menu=AlignedMenu(self)
        menu.addAction('时钟设置…').triggered.connect(self.open_settings)
        menu.addAction('时光进度与倒计时…').triggered.connect(self.open_progress)
        menu.addAction('翻到时钟' if self.flipped else '翻到月历').triggered.connect(self.flip)
        styles=menu.addMenu('时钟样式')
        for title,style in STYLES:
            action=styles.addAction(title);action.setCheckable(True);action.setChecked(self.option('style')==style)
            action.triggered.connect(lambda checked=False,s=style:self.set_style(s))
        menu.addSeparator()
        if self.parentWidget() is None:
            locked=menu.addAction('锁定位置与大小');locked.setCheckable(True);locked.setChecked(self.option('locked'))
            locked.triggered.connect(self.set_locked)
        menu.addAction('隐藏时钟').triggered.connect(lambda:self.set_enabled(False))
        return menu
    def contextMenuEvent(self,event):
        menu=self.build_menu();menu.exec_(event.globalPos());menu.deleteLater()

    def place_controls(self):
        self.position_flip()

    def position_flip(self):
        if hasattr(self,'flip_button'):
            ratio=max(2.0,self.devicePixelRatioF())
            ink=getattr(self,'_control_ink','#506378')
            key=(ratio,ink)
            if getattr(self,'_flip_icon_key',None)!=key:
                pixmap=QPixmap(round(12*ratio),round(12*ratio));pixmap.setDevicePixelRatio(ratio);pixmap.fill(Qt.transparent)
                painter=QPainter(pixmap);painter.scale(2,2);painter.setRenderHint(QPainter.Antialiasing);painter.setPen(QPen(QColor(ink),.7,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
                painter.drawLine(QPointF(.6,3),QPointF(5.4,3))
                for x,direction in ((.6,1),(5.4,-1)):
                    painter.drawLine(QPointF(x+1.4*direction,1.6),QPointF(x,3));painter.drawLine(QPointF(x,3),QPointF(x+1.4*direction,4.4))
                painter.end();self.flip_button.setIcon(QIcon(pixmap));self._flip_icon_key=key

            self.flip_button.move(self.width()-26,14)

    def flip(self):
        if self.kind!='clock' or self.flip_progress is not None:return
        self._flip_from=self.flipped;self._flip_to=not self.flipped;self.flip_progress=0;self.flip_animation.start()

    def advance_flip(self,value):self.flip_progress=float(value);self.update()
    def finish_flip(self):
        self.flipped=self._flip_to if self.save(clock_flipped=self._flip_to) else self._flip_from
        self.flip_progress=None;self.update_time()

    def draw_options(self,**values):
        options=dict(self.option('appearance'),**values)
        if self.parentWidget() is not None:
            host=self.runtime.resources.window
            if host is not None and self.window() is host:
                options.update(host.background,_host_palette=host.colors)
                options['design']=self.dock.cfg['card_design']
                if self.dock.cfg['resource_background']=='custom':
                    options['design']=material_design(options['material'],options['design'])
        return options

    def paint_face(self,painter,style,**values):
        ink=draw_clock(painter,QRectF(self.rect()).adjusted(1,1,-1,-1),self.dock,
                       self.draw_options(**values),style,self.backdrop)
        painter.end()
        if ink!=getattr(self,'_control_ink',None):
            self._control_ink=ink
            self.place_controls()

    def paintEvent(self,event):
        import math
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing);painter.setRenderHint(QPainter.SmoothPixmapTransform);painter.setRenderHint(QPainter.TextAntialiasing)
        self.paint_resize_targets(painter)
        face=getattr(self,'flipped',False)
        if getattr(self,'flip_progress',None) is not None:
            face=self._flip_to if self.flip_progress>=.5 else self._flip_from
            painter.translate(self.width()/2,0);painter.scale(max(.015,abs(math.cos(math.pi*self.flip_progress))),1);painter.translate(-self.width()/2,0)
        self.paint_face(painter,'calendar_card' if face else self.option('style'),_header_controls=self.kind=='clock')

    def paint_resize_targets(self,painter):
        if self.can_drag():paint_edge_targets(painter,self.rect())

    def dispose(self,save_geometry=True):
        if self.closed:return
        if hasattr(self,'flip_animation'):self.flip_animation.stop()
        if self.geometry_timer.isActive():
            self.geometry_timer.stop()
            if save_geometry:self.save_geometry()
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
    material=options['material'];host=options.get('_host_palette')
    design=options['design'] if options['design']!='follow' else dock.cfg.get('card_design','aurora')
    options['design']=design
    decorate=material!='solid' or design!='minimal'
    mode='light' if material!='clear' and decorate and design in ('gradient','paper','minimal') else options['theme']
    colors=material_palette(tint_palette(dock.base_theme_colors(mode),options['color']),material) if not host else host
    radius=min(options['corner_radius'],h*.24)
    shape=QPainterPath()
    if host:shape.addRect(rect)
    else:shape.addRoundedRect(rect,radius,radius)
    paint_surface=None
    if not host and material!='clear':
        from card_design import paint_design
        style_cfg=dict(dock.cfg,theme_color=options['color'] or '#b8d9ef')
        strength=options['highlight']/45
        colors['border'].setAlpha(min(255,round(colors['border'].alpha()*strength)))
        stops=[(position,min(255,round(alpha*strength))) for position,alpha in dock.merged_grad_stops(colors)]
        surface=SimpleNamespace(cfg={'glass':material!='solid','dock_material':material},backdrop=backdrop,spec_x=0,spec_alpha=0)

        def paint_surface(target):
            paint_liquid_glass(surface,target,shape,rect,rect,colors,int(options['opacity']*2.55),stops)
            if decorate:
                paint_design(target,rect,style_cfg,design,corner_radius=radius,body_top=rect.bottom(),header_separator=False)

        paint_surface(painter)
    painter.setClipPath(shape)
    light=colors['light']
    ink=QColor(options['text_color'] or (LIGHT_GLASS_INK if light else '#ffffff'))
    muted=QColor(ink)
    from clock_legibility import surface_map,background_at,readable,contrast,neutral_text
    analysis=None
    samples=[]
    if options['auto_contrast']:
        if host:
            ink,muted=QColor(host['ink']),QColor(host['muted'])
            samples=[QColor(host['surface'])]
        else:
            surface_keys=('material','color','opacity','highlight','corner_radius')
            key=(w,h,backdrop.cacheKey() if backdrop is not None else 0,light,design,tuple(options[k] for k in surface_keys))
            fallback=QColor(colors['tint'])
            analysis=surface_map(key,w,h,backdrop,fallback,paint_surface)
            samples=background_at(analysis,rect,w,h)
            ink,muted=neutral_text(samples)
    if options['accent_color']:accent=QColor(options['accent_color'])
    else:
        seed=THEME_ACCENTS.get(theme_family(options),options['color'] or '#62acd4')
        hue=QColor(seed).hslHueF()
        accent=QColor.fromHslF(hue if hue>=0 else .57,.68,.74 if ink.lightness()>150 else .36)
    accent_text=readable(accent,samples,4.5,polarity=ink.lightness()>150) if samples else accent
    now=options.get('_now') or datetime.datetime.now();time_text,period=format_clock_time(now,options['hour_format'])
    hour=int(time_text[:2])
    date_text='%d月%d日  周%s'%(now.month,now.day,'一二三四五六日'[now.weekday()]);scale=options['font_scale']/100
    margin=max(9,w*.075)
    def font(size,weight=QFont.Normal):
        f=QFont(options['font']);f.setPixelSize(max(8,round(size)));f.setWeight(options['font_weight'] if size>=21 else weight)
        if size>=21:f.setLetterSpacing(QFont.PercentageSpacing,options['letter_spacing']);f.setStretch(100)
        f.setStyleStrategy(QFont.PreferAntialias);f.setHintingPreference(QFont.PreferVerticalHinting);return f
    def text(box,value,size,color,weight=QFont.Normal,align=Qt.AlignLeft|Qt.AlignVCenter,fit=True):
        f=font(size,weight)
        digital=style=='digital' and value and all(character in '0123456789:' for character in value)
        if digital and options['font']=='Segoe UI':
            f.setFamily('Consolas')
            if f.pixelSize()<21:f.setWeight(weight)
        elif any('\u3400'<=character<='\u9fff' for character in value) or (size<21 and not (style in ('month','calendar_card') and value.isdigit())):
            f.setFamily(options['date_font']);f.setPixelSize(max(8,round(f.pixelSize()*options['date_scale']/100)));f.setStretch(100);f.setLetterSpacing(QFont.PercentageSpacing,100);f.setWeight(weight)
        if fit:
            while f.pixelSize()>8 and (QFontMetricsF(f).horizontalAdvance(value)>box.width() or QFontMetricsF(f).tightBoundingRect(value).height()>box.height()):f.setPixelSize(f.pixelSize()-1)
        painter.setFont(f)
        # Soft offset shadows improve contrast without outlining each glyph.
        from PyQt5.QtGui import QLinearGradient
        metrics=QFontMetricsF(f);width=metrics.horizontalAdvance(value)
        x=box.x()+(box.width()-width)/2 if align & Qt.AlignHCenter else box.right()-width if align & Qt.AlignRight else box.x()
        tight=metrics.tightBoundingRect(value)
        baseline=box.y()+(box.height()-tight.height())/2-tight.top()
        shadows=((1.0,25),) if options['shadow']=='soft' and f.pixelSize()>=20 else ()
        color=QColor(accent_text if QColor(color)==accent else color)
        color.setAlpha(round(color.alpha()*options['text_opacity']/100))
        text_rect=QRectF(x,baseline+tight.top(),max(1,width),max(1,tight.height()))
        if analysis is not None and color.alpha()>=120:
            local_background=background_at(analysis,text_rect,w,h)
            if min(contrast(color,bg) for bg in local_background)<4.0 and color.lightness()>150:
                shadows=((1.0,65),(2.0,24))
        for offset,opacity in shadows:
            shadow=QColor('#10253a');shadow.setAlpha(opacity)
            painter.setPen(shadow);painter.drawText(QPointF(x,baseline+offset),value)
        if '_text_audit' in options:options['_text_audit'].append((value,f.pixelSize(),color.name(),color.alpha(),text_rect.getRect()))
        if options['text_effect']=='clear' or f.pixelSize()<18:
            painter.setPen(color);painter.drawText(QPointF(x,baseline),value)
            return text_rect
        # Background sampling and the glass tint remain clipped to the glyph.
        glyph=QPainterPath();glyph.addText(QPointF(x,baseline),f,value)
        painter.save();painter.setClipPath(glyph,Qt.IntersectClip)
        if backdrop is not None and not backdrop.isNull():
            painter.drawPixmap(QRectF(0,0,w,h),backdrop,QRectF(0,0,backdrop.width(),backdrop.height()))
        bounds=glyph.boundingRect();wash=QLinearGradient(0,bounds.top(),0,bounds.bottom())
        upper=color.lighter(110) if color.lightness()<150 else QColor(color)
        upper.setAlpha(color.alpha());lower=QColor(color);lower.setAlpha(round(color.alpha()*.97))
        wash.setColorAt(0,upper);wash.setColorAt(1,lower);painter.fillRect(bounds,wash);painter.restore()
        return text_rect
    from clock_design import draw
    draw(style,painter,w,h,now,options,ink,muted,accent,text,time_text,period)
    painter.restore()
    return muted.name()


from clock_options import ClockOptions,ClockPreview
