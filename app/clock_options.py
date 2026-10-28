"""Grouped clock controls with a pinned preview and independent work schedules."""
import copy,json,re,datetime
from pathlib import Path
from PyQt5.QtCore import Qt,QRectF
from PyQt5.QtGui import QPainter,QColor,QFontDatabase,QLinearGradient
from PyQt5.QtWidgets import QWidget,QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QScrollArea,QLineEdit,QColorDialog,QComboBox,QTabWidget,QGridLayout,QPlainTextEdit,QFileDialog
from ui_style import SettingsHeader,ModernComboBox,ModernSpinBox,ModernCheckBox,ThemeSwatches,button,label,compact_dialog
from clock_appearance import STYLES,FONTS,PRESETS,DEFAULTS,normalize
from appearance_presets import MATERIALS,COLOR_MODES
import work_schedule


class ClockPreview(QWidget):
    def __init__(self,dialog):
        super().__init__();self.dialog=dialog;self.setMinimumSize(200,125);self.setFixedHeight(210)
    def paintEvent(self,event):
        from desktop_clock import draw_clock
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        fill=QLinearGradient(0,0,self.width(),self.height());fill.setColorAt(0,QColor('#87b6d3'));fill.setColorAt(1,QColor('#99a9cc'))
        painter.setPen(Qt.NoPen);painter.setBrush(fill);painter.drawRoundedRect(QRectF(self.rect()),12,12)
        ratio=self.dialog.fields['width'].value()/max(1,self.dialog.fields['height'].value())
        h=min(self.height()-18,(self.width()-24)/ratio);w=h*ratio
        clock=self.dialog.clock;o=self.dialog.values()
        if clock.kind=='calendar':o=dict(o,_calendar_year=clock.view_year,_calendar_month=clock.view_month)
        logical_width=self.dialog.fields['width'].value();logical_height=self.dialog.fields['height'].value()
        painter.save();painter.translate((self.width()-w)/2,(self.height()-h)/2);painter.scale(w/logical_width,h/logical_height)
        draw_clock(painter,QRectF(0,0,logical_width,logical_height),clock.dock,o,'calendar_card' if clock.kind=='calendar' else self.dialog.fields['style'].currentData());painter.restore()


class ClockOptions(QDialog):
    def __init__(self,clock):
        super().__init__(clock,Qt.Window|Qt.FramelessWindowHint|Qt.WindowMinimizeButtonHint)
        self.clock=clock;self.fields={};self.loading=True;self.calendar=clock.kind=='calendar';self.imported_calendars=copy.deepcopy(clock.option('appearance')['work']['calendars'])
        self.setWindowTitle(clock.component_name+'设置 · 大肥鱼Dock');self.resize(740,820);self.setMinimumSize(500,540)
        body=QVBoxLayout(self);body.addWidget(SettingsHeader(self,clock.component_name+'设计'))
        body.addWidget(label('先选样式，再调整文字、背景与工作时间。预览与桌面使用相同绘图。','muted'))
        self.preview=ClockPreview(self);body.addWidget(self.preview);self.tabs=QTabWidget();body.addWidget(self.tabs,1)
        def page(title):
            scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.NoFrame);widget=QWidget();form=QFormLayout(widget);form.setVerticalSpacing(8);form.setContentsMargins(12,12,12,12);scroll.setWidget(widget);self.tabs.addTab(scroll,title);return form
        layout=page('样式布局');typeform=page('文字配色');material=page('背景材质');workform=page('工作时间')
        def choice(form,key,title,items,visible=True):
            field=ModernComboBox();field.setAccessibleName(title)
            for name,value in items:field.addItem(name,value)
            self.fields[key]=field
            if visible:form.addRow(title,field)
            return field
        def number(form,key,title,low,high):
            field=ModernSpinBox();field.setRange(low,high);field.setAccessibleName(title);self.fields[key]=field;form.addRow(title,field);return field
        def check(form,key,title):
            field=ModernCheckBox(title);self.fields[key]=field;form.addRow('',field);return field
        self.preset=ModernComboBox();self.preset.addItem('自定义 / 保留当前设置')
        for name,_ in PRESETS:self.preset.addItem(name)
        layout.addRow('配色方案',self.preset)
        self.style_buttons=[]
        if not self.calendar:
            style=choice(layout,'style','样式',STYLES,False);grid=QGridLayout()
            for i,(name,value) in enumerate(STYLES):
                item=button(name,lambda checked=False,v=value:style.setCurrentIndex(style.findData(v)));item.setCheckable(True);item.setObjectName('ClockStyle');item.setStyleSheet('QPushButton#ClockStyle {font-weight:600;} QPushButton#ClockStyle:checked {background:rgba(95,164,204,45);border:1px solid rgba(95,164,204,110);color:palette(text);}')
                item.setMinimumHeight(34);self.style_buttons.append((item,value));grid.addWidget(item,i//3,i%3)
            layout.addRow(grid)
            choice(layout,'layout','布局方向',[('自动适配窗口','auto'),('横向','wide'),('纵向','portrait')])
            choice(layout,'align','数字对齐',[('左对齐','left'),('居中','center')])
            choice(layout,'hour_format','时间格式',[('24 小时','24'),('12 小时','12')])
        self.show_date=ModernCheckBox('显示附加日期与星期')
        if not self.calendar:layout.addRow('',self.show_date)
        dimensions=QHBoxLayout();self.fields['width']=ModernSpinBox();self.fields['width'].setRange(clock.minimum[0],2400);self.fields['height']=ModernSpinBox();self.fields['height'].setRange(clock.minimum[1],1600)
        dimensions.addWidget(label('宽'));dimensions.addWidget(self.fields['width']);dimensions.addWidget(label('高'));dimensions.addWidget(self.fields['height']);layout.addRow('组件尺寸',dimensions)
        number(layout,'padding','内容留白（%）',4,14);number(layout,'corner_radius','背景圆角',8,36)
        fonts=FONTS+[(family,family) for family in QFontDatabase().families() if family not in {v for _,v in FONTS}]
        choice(typeform,'font','时间字体',fonts);choice(typeform,'date_font','辅助文字字体',fonts)
        number(typeform,'font_scale','时间字号（%）',60,180);number(typeform,'date_scale','辅助字号（%）',70,150)
        choice(typeform,'font_weight','时间字重',[('常规',50),('中等',57),('半粗',63),('加粗',75),('特粗',81)])
        number(typeform,'letter_spacing','数字字距（%）',90,115)
        choice(typeform,'text_effect','文字效果',[('清晰实色','clear'),('细腻玻璃','glass')]);choice(typeform,'shadow','文字阴影',[('无阴影','none'),('轻柔阴影','soft')])
        def color(form,key,title):
            field=QLineEdit();field.setPlaceholderText('自动 / #RRGGBB');field.setAccessibleName(title);self.fields[key]=field
            box=QVBoxLayout();row=QHBoxLayout();row.addWidget(field,1);row.addWidget(button('选色',lambda:self.choose_color(field)));row.addWidget(button('自动',lambda:field.clear()));box.addLayout(row);box.addWidget(ThemeSwatches(field));form.addRow(title,box)
        color(typeform,'text_color','主要文字');color(typeform,'accent_color','强调与进度');number(typeform,'text_opacity','文字不透明度（%）',50,100)
        check(typeform,'auto_contrast','自动提高文字与强调色的对比度')
        from card_design import DESIGNS
        choice(material,'design','卡片风格',[('跟随卡片风格','follow')]+DESIGNS);choice(material,'material','背景材质',MATERIALS);choice(material,'theme','明暗模式',COLOR_MODES)
        color(material,'color','背景主题色');number(material,'opacity','背景不透明度（%）',0,100);number(material,'blur','模糊强度',2,30);number(material,'highlight','高光（%）',0,100)
        number(layout,'bar_width','进度条厚度',4,18);number(layout,'ring_width','圆环厚度',4,18)
        choice(layout,'ring_mode','进度圆环',[('今日进度','day'),('下班进度','work')])
        for key,title in [('show_work','时光进度：显示下班进度'),('show_week','显示本周进度'),('show_month','显示本月进度'),('show_year','显示本年进度')]:check(layout,key,title)
        def timefield(key,value):
            field=QLineEdit(value);field.setInputMask('00:00;_');field.setMaximumWidth(110);field.setToolTip('24 小时 HH:mm，例如 09:00；下班早于上班时按跨夜班次计算。');self.fields[key]=field;return field
        row=QHBoxLayout();row.addWidget(label('上班'));row.addWidget(timefield('start','09:00'));row.addWidget(label('下班'));row.addWidget(timefield('end','18:00'));row.addStretch();workform.addRow('班次时间',row)
        choice(workform,'calendar','工作日历',[('中国大陆节假日与调休','cn'),('只按工作周','weekdays'),('每天均为工作日','daily')])
        self.weekdays=[];row=QHBoxLayout()
        for i,name in enumerate('一二三四五六日'):
            field=button(name,lambda:None);field.setCheckable(True);field.setObjectName('ClockWeekday');field.setFixedWidth(42);field.setStyleSheet('QPushButton#ClockWeekday:checked {background:palette(highlight);color:palette(highlighted-text);border-color:palette(highlight);font-weight:600;}');self.weekdays.append(field);row.addWidget(field)
        row.addStretch();workform.addRow('工作周',row)
        check(workform,'break_enabled','计算进度时扣除班内休息时间')
        row=QHBoxLayout();row.addWidget(timefield('break_start','12:00'));row.addWidget(label('至'));row.addWidget(timefield('break_end','13:00'));row.addStretch();workform.addRow('休息时段',row)
        for key,title in [('rest_dates','额外休息日'),('work_dates','额外上班日')]:
            field=QPlainTextEdit();field.setMaximumHeight(60);field.setPlaceholderText('YYYY-MM-DD，多日用逗号或换行分隔');self.fields[key]=field;workform.addRow(title,field)
        self.calendar_info=label('','muted');self.calendar_info.setWordWrap(True);workform.addRow(self.calendar_info)
        row=QHBoxLayout();row.addWidget(button('导入…',self.import_calendar));self.calendar_years=ModernComboBox();row.addWidget(self.calendar_years,1);self.remove_calendar_button=button('移除导入',self.remove_calendar);row.addWidget(self.remove_calendar_button);workform.addRow('年度日历',row)
        workform.addRow(label('调休优先于普通周末，自定义日期优先于节假日。跨夜按上班当天判断。导入全年日历会替代该年内置安排。','muted'))
        self.status=label('保存后立即应用；关闭不会提交未保存的修改。','muted');self.status.setWordWrap(True);body.addWidget(self.status)
        row=QHBoxLayout();row.addStretch();row.addWidget(button('关闭',self.reject));row.addWidget(button('保存设置',self.commit,'primary'));body.addLayout(row)
        saved=clock.option('appearance');work=saved['work']
        for key,field in self.fields.items():
            if key=='style':value=clock.option('style')
            elif key=='width':value=clock.width()
            elif key=='height':value=clock.height()
            elif key in work:value=work[key]
            else:value=saved[key]
            if isinstance(field,QComboBox):
                if field.findData(value)<0:field.addItem(str(value),value)
                field.setCurrentIndex(max(0,field.findData(value)))
            elif isinstance(field,QLineEdit):field.setText(value)
            elif isinstance(field,QPlainTextEdit):field.setPlainText('\n'.join(value))
            elif isinstance(field,ModernCheckBox):field.setChecked(value)
            else:field.setValue(value)
        for i,field in enumerate(self.weekdays):field.setChecked(i in work['weekdays']);field.toggled.connect(self.changed)
        self.show_date.setChecked(saved['show_date']);self.loading=False
        for field in self.fields.values():
            signal=field.currentIndexChanged if isinstance(field,QComboBox) else field.textChanged if isinstance(field,(QLineEdit,QPlainTextEdit)) else field.toggled if isinstance(field,ModernCheckBox) else field.valueChanged
            signal.connect(self.changed)
        self.preset.currentIndexChanged.connect(self.apply_preset);self.show_date.toggled.connect(self.changed);self.changed()
        compact_dialog(self)
        from settings_layout import fit_auxiliary_dialog
        fit_auxiliary_dialog(self,clock.dock.cfg)
    def work_values(self,strict=False):
        def parse(key):return [part for part in re.split(r'[\s,，;；]+',self.fields[key].toPlainText().strip()) if part]
        values={key:self.fields[key].text() for key in ('start','end','break_start','break_end')}
        values.update(calendar=self.fields['calendar'].currentData(),weekdays=[i for i,field in enumerate(self.weekdays) if field.isChecked()],break_enabled=self.fields['break_enabled'].isChecked(),rest_dates=parse('rest_dates'),work_dates=parse('work_dates'),calendars=copy.deepcopy(self.imported_calendars))
        return work_schedule.normalize(values,strict)
    def values(self):
        values={}
        for key in DEFAULTS:
            field=self.fields.get(key)
            if field is None:continue
            values[key]=field.currentData() if isinstance(field,QComboBox) else field.text().strip() if isinstance(field,QLineEdit) else field.isChecked() if isinstance(field,ModernCheckBox) else field.value()
        values.update(show_date=self.show_date.isChecked(),work=self.work_values(),typography_version=2)
        return normalize(values)
    def changed(self,*args):
        if self.loading:return
        if self.preset.currentIndex():self.preset.blockSignals(True);self.preset.setCurrentIndex(0);self.preset.blockSignals(False)
        for item,value in self.style_buttons:item.setChecked(self.fields['style'].currentData()==value)
        if not self.calendar:
            style=self.fields['style'].currentData()
            for key in ('show_work','show_week','show_month','show_year','bar_width','ring_mode'):self.fields[key].setEnabled(style=='orbit')
            self.fields['ring_width'].setEnabled(style in ('orbit','analog'))
            self.fields['align'].setEnabled(style=='digital');self.fields['layout'].setEnabled(style in ('analog','stacked','calendar','orbit'))
            self.show_date.setEnabled(style in ('digital','analog','stacked'))
        year=datetime.date.today().year;known=str(year) in self.imported_calendars or work_schedule.builtin(year) is not None
        self.calendar_info.setText(('%d 年节假日已收录，含法定调休。'%year if known else '%d 年节假日未收录，暂按工作周计算。'%year)+' 可导入其他年度；自定义日历按所选文件使用。')
        selected=self.calendar_years.currentData();self.calendar_years.blockSignals(True);self.calendar_years.clear()
        for year in sorted(self.imported_calendars):self.calendar_years.addItem(year+' 年 · 自定义',year)
        if not self.imported_calendars:self.calendar_years.addItem('未导入自定义年度',None)
        if self.calendar_years.findData(selected)>=0:self.calendar_years.setCurrentIndex(self.calendar_years.findData(selected))
        self.calendar_years.blockSignals(False);self.remove_calendar_button.setEnabled(bool(self.imported_calendars))
        self.preview.update()
    def remove_calendar(self):
        year=self.calendar_years.currentData()
        if year in self.imported_calendars:
            del self.imported_calendars[year];self.changed();self.status.setText('已移除 '+year+' 年导入，保存后恢复内置安排或工作周规则。')
    def apply_preset(self,index):
        if self.loading or index<=0:return
        self.loading=True
        for key,value in PRESETS[index-1][1].items():
            field=self.fields[key]
            if isinstance(field,QComboBox):field.setCurrentIndex(field.findData(value))
            elif isinstance(field,QLineEdit):field.setText(value)
            else:field.setValue(value)
        self.loading=False;self.preview.update()
    def choose_color(self,field):
        value=QColorDialog.getColor(QColor(field.text() or '#b8d9ef'),self,'选择颜色')
        if value.isValid():field.setText(value.name())
    def import_calendar(self):
        path,_=QFileDialog.getOpenFileName(self,'导入年度日历','','年度日历 (*.json)')
        if not path:return
        try:
            file=Path(path)
            if file.stat().st_size>1024*1024:raise ValueError('日历文件超过 1 MiB。')
            data=work_schedule.validate_calendar(json.loads(file.read_text(encoding='utf-8-sig')))
            if len(self.imported_calendars)>=20 and str(data['year']) not in self.imported_calendars:raise ValueError('最多保留 20 份年度日历。')
            self.imported_calendars[str(data['year'])]=data;self.changed();self.status.setText('%d 年日历已载入，保存设置后生效。'%data['year'])
        except (ValueError,OSError) as error:self.status.setText(str(error))
    def commit(self):
        for key in ('color','text_color','accent_color'):
            value=self.fields[key].text().strip()
            if value and not re.fullmatch(r'#[0-9a-fA-F]{6}',value):self.status.setText('颜色请使用 #RRGGBB，或留空自动配色。');return False
        try:work=self.work_values(True)
        except (ValueError,TypeError) as error:self.status.setText(str(error));self.tabs.setCurrentIndex(3);return False
        from screen_layout import capture,screen_records
        rect=list(self.clock.geometry().getRect());rect[2:]=[self.fields['width'].value(),self.fields['height'].value()]
        layout=capture(rect,screen_records(),density=self.clock.dock.cfg.get('card_scale',70)/100)
        options=self.values();options['work']=work
        changes=dict(clock_appearance=options,clock_layout=layout)
        if not self.calendar:changes['clock_style']=self.fields['style'].currentData()
        if self.clock.save(**changes):
            self.clock.reposition();self.clock.sync();self.status.setText('已保存并应用'+self.clock.component_name+'设置。');return True
        self.status.setText('保存失败，原设置保持不变。');return False
