"""Light grouped settings, using the existing Qt controls and save semantics."""
from PyQt5.QtCore import Qt, QSize, QTimer, QEvent, QRectF
from PyQt5.QtGui import QPainter, QColor, QPen, QFont, QPalette
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QFormLayout, QLabel, QCheckBox, QSpinBox, QSlider, QLineEdit, QComboBox,
    QPlainTextEdit, QScrollArea, QSizePolicy, QApplication, QLayout, QStyle, QStyleOptionSlider)


def section_marker(form, text):
    from ui_style import label
    heading = label(text, 'section')
    heading.setProperty('settingsGroup', True)
    form.addRow(heading)


class ResponsiveFields(QWidget):
    """Two columns at normal width, a single column without smaller text."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(12)
        self.grid.setSizeConstraint(QLayout.SetNoConstraint)
        self.cells = []
        self.columns = 0
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def minimumSizeHint(self):
        return QSize(0, self.grid.minimumSize().height())

    def fit_height(self):
        height=max(self.grid.minimumSize().height(),self.grid.heightForWidth(max(1,self.width())))
        if self.minimumHeight()!=height:self.setMinimumHeight(height)

    def event(self,event):
        result=super().event(event)
        if hasattr(self,'grid') and event.type() in (QEvent.LayoutRequest,QEvent.FontChange,QEvent.StyleChange):
            self.fit_height()
        return result

    def add(self, widget, wide=False):
        self.cells.append((widget, wide))
        self.arrange()

    def arrange(self):
        from ui_style import widget_px
        columns = 2 if self.width() >= widget_px(self, 410) else 1
        if self.columns == columns and self.grid.count() == len(self.cells):
            self.fit_height()
            return
        self.columns = columns
        while self.grid.count():
            self.grid.takeAt(0)
        row = column = 0
        for widget, wide in self.cells:
            if wide and column:
                self.grid.addWidget(previous, row, 0, 1, columns)
                row += 1
                column = 0
            self.grid.addWidget(widget, row, column, 1, columns if wide else 1)
            if wide or column + 1 == columns:
                row += 1
                column = 0
            else:
                column += 1
            previous = widget
        if column:
            self.grid.addWidget(previous, row, 0, 1, columns)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1 if columns == 2 else 0)
        self.fit_height()
        self.updateGeometry()

    def resizeEvent(self, event):
        self.arrange()
        super().resizeEvent(event)


class SettingsSlider(QSlider):
    """Native slider input with a flat, antialiased track and thumb."""
    def paintEvent(self,event):
        from ui_style import widget_px
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        light=self.palette().color(QPalette.Window).lightness()>128
        option=QStyleOptionSlider();self.initStyleOption(option)
        handle=self.style().subControlRect(QStyle.CC_Slider,option,QStyle.SC_SliderHandle,self)
        radius=widget_px(self,5);margin=radius+1;cy=self.height()/2
        x=max(margin,min(self.width()-margin,handle.center().x()))
        track=QRectF(margin,cy-widget_px(self,2),max(0,self.width()-2*margin),widget_px(self,4))
        ink=QColor('#438aa7') if self.isEnabled() else self.palette().color(QPalette.Mid)
        p.setPen(Qt.NoPen);p.setBrush(QColor('#e4ebef' if light else '#42494e'));p.drawRoundedRect(track,2,2)
        p.setBrush(ink)
        filled=QRectF(track)
        if option.upsideDown:filled.setLeft(x)
        else:filled.setRight(x)
        p.drawRoundedRect(filled,2,2);p.drawEllipse(QRectF(x-radius,cy-radius,2*radius,2*radius))
        if self.hasFocus() and self.testAttribute(Qt.WA_KeyboardFocusChange):
            p.setPen(QPen(self.palette().color(QPalette.Text),1));p.setBrush(Qt.NoBrush)
            p.drawEllipse(QRectF(x-radius-2,cy-radius-2,2*radius+4,2*radius+4))


class NumericControl(QWidget):
    def __init__(self, spin):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.slider = SettingsSlider(Qt.Horizontal)
        self.slider.setRange(spin.minimum(), spin.maximum())
        self.slider.setValue(spin.value())
        self.slider.setAccessibleName(spin.accessibleName() + '滑块')
        self.slider.setFocusPolicy(Qt.StrongFocus)
        spin.setMinimumWidth(94)
        spin.setMaximumWidth(120)
        layout.addWidget(self.slider, 1)
        layout.addWidget(spin)
        self.slider.valueChanged.connect(spin.setValue)
        spin.valueChanged.connect(self.slider.setValue)
        self.setFocusProxy(spin)


class DockPreview(QWidget):
    """Small event-driven preview: no timer, wallpaper capture or icon loading."""
    def __init__(self, dialog):
        super().__init__()
        self.dialog = dialog
        self.setObjectName('SettingsPreview')
        self.setAccessibleName('Dock 外观预览')
        self.setFixedHeight(88)
        for key in ('theme_color','transparency','dock_highlight'):
            field=dialog.fields[key]
            if isinstance(field, QComboBox):
                field.currentIndexChanged.connect(self.update)
            elif isinstance(field, QSpinBox):
                field.valueChanged.connect(self.update)
            elif isinstance(field, QLineEdit):
                field.textChanged.connect(self.update)
            elif isinstance(field, QCheckBox):
                field.toggled.connect(self.update)

    def sizeHint(self):
        from ui_style import widget_px
        return QSize(widget_px(self, 420), widget_px(self, 96))

    def paintEvent(self, event):
        from PyQt5.QtCore import QRectF
        from ui_style import widget_px
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        light = self.palette().color(QPalette.Window).lightness() > 128
        p.setPen(Qt.NoPen)
        p.setBrush(QColor('#e5f1f7' if light else '#283139'))
        p.drawRoundedRect(QRectF(self.rect()), 10, 10)
        fields = self.dialog.fields
        color = QColor(fields['theme_color'].text() or '#8fbfe0')
        if not color.isValid(): color = QColor('#8fbfe0')
        p.setPen(self.palette().color(QPalette.Text))
        font = self.font(); font.setPixelSize(widget_px(self, 12)); p.setFont(font)
        p.drawText(widget_px(self, 14), widget_px(self, 22), '外观预览')
        strip = QRectF(widget_px(self, 14), widget_px(self, 35), self.width()-widget_px(self, 28), self.height()-widget_px(self, 46))
        fill = QColor(color); fill.setAlpha(max(18, round(fields['transparency'].value()*1.8)))
        p.setPen(QPen(QColor(255,255,255,round(fields['dock_highlight'].value()*2)), 1))
        p.setBrush(fill); p.drawRoundedRect(strip, 10, 10)
        from dock_extras import symbol
        size = min(widget_px(self, 23), max(14, (strip.width()-100)/6))
        symbols = ['apps', 'size', 'notes', 'clock']
        x = strip.center().x() - size*3.8
        for kind in symbols:
            symbol(p, QRectF(x, strip.center().y()-size/2, size, size), kind, color.darker(140))
            x += size*1.65
        font.setPixelSize(widget_px(self, 13)); font.setWeight(QFont.DemiBold); p.setFont(font)
        p.setPen(self.palette().color(QPalette.Text))
        p.drawText(QRectF(x,strip.top(),size*2.8,strip.height()),Qt.AlignCenter,'10:30')


def _item_widget(item):
    if item is None:
        return None
    if item.widget() is not None:
        return item.widget()
    if item.layout() is not None:
        layout = item.layout()
        layout.setParent(None)
        widget = QWidget()
        widget.setLayout(layout)
        return widget
    return None


def group_form(form, dialog):
    """Move existing controls, retaining identity, signals and validation."""
    if form.property('lightGroupsApplied'):
        return
    form.setProperty('lightGroupsApplied', True)
    rows = []
    while form.rowCount():
        row = form.takeRow(0)
        rows.append((_item_widget(row.labelItem), _item_widget(row.fieldItem)))
    form.setContentsMargins(10, 8, 10, 10) if dialog.objectName()=='SettingsDialog' else form.setContentsMargins(0, 4, 4, 8)
    form.setVerticalSpacing(14)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.DontWrapRows)
    fields = None
    for caption, field in rows:
        if field is None:
            field, caption = caption, None
        if field is None:
            continue
        if caption is None and isinstance(field,QCheckBox):
            caption=QLabel('')
        if caption is None:
            fields = None
            form.addRow(field)
            continue
        title = caption.text() if isinstance(caption, QLabel) else ''
        if isinstance(field,QComboBox):
            field.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            field.setMinimumContentsLength(8)
            field.setMinimumWidth(0)
        if not title and not isinstance(field, QCheckBox):
            caption.deleteLater()
            fields = None
            form.addRow(field)
            continue
        if fields is None:
            fields = ResponsiveFields()
            form.addRow(fields)
        cell = QWidget()
        cell.setObjectName('SettingsField')
        layout = QVBoxLayout(cell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        if title:
            caption.setMinimumWidth(0)
            caption.setMaximumWidth(16777215)
            caption.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            caption.setProperty('role', 'field-label')
            layout.addWidget(caption)
            if isinstance(field, (QLineEdit, QSpinBox, QComboBox)):
                caption.setBuddy(field)
        else:
            caption.deleteLater()
        slider = isinstance(field,QSpinBox) and any(word in title for word in ('高光','不透明度','模糊强度','字号','图标大小','宽度比例'))
        layout.addWidget(NumericControl(field) if slider else field)
        wide = (not isinstance(field, (QComboBox,QSpinBox,QCheckBox)) or
                any(word in title for word in ('预设','配色方案')) or
                any(word in title for word in ('路径','地址','链接','字体','格式','目录','时段')))
        fields.add(cell, wide)


def prepare_dialog(dialog):
    if dialog.property('lightGroupsPrepared'):
        return
    dialog.setProperty('lightGroupsPrepared', True)
    dialog.setProperty('designPopup', True)
    owner=dialog.parentWidget()
    if owner is not None:
        # Component-local styles must not cascade into a settings window when
        # saving repolishes its owner (especially the note editor's text rules).
        owner_handle=owner.windowHandle()
        dialog.setParent(None,dialog.windowFlags())
        if owner_handle is not None:
            dialog.winId()
            dialog.windowHandle().setTransientParent(owner_handle)
    # Snapshot before rebuilding, so newly added layouts are never processed twice.
    for form in list(dialog.findChildren(QFormLayout)):
        if form.parentWidget() and form.parentWidget().window() is dialog:
            group_form(form, dialog)
    from ui_style import SettingsHeader
    body = dialog.layout()
    if not isinstance(body, QVBoxLayout):
        return
    if dialog.objectName() == 'SettingsDialog':
        dialog.tabs.pages.setObjectName('SettingsSheet')
        dialog.tabs.pages.setContentsMargins(8,8,8,8)
        dialog.tabs.layout().setSpacing(8)
        return
    header_index = next((i for i in range(body.count()) if isinstance(body.itemAt(i).widget(),SettingsHeader)), None)
    if header_index is None:
        return
    # Keep the real footer outside the white sheet. Some managers have a status
    # label after the action row; that label stays in the footer as well.
    footer_index = body.count()
    for i in range(body.count()-1, header_index, -1):
        item = body.itemAt(i)
        if isinstance(item.layout(), QHBoxLayout):
            buttons = [item.layout().itemAt(j).widget() for j in range(item.layout().count())]
            if any(w is not None and hasattr(w,'text') and w.text() in ('关闭','取消','确定') for w in buttons):
                footer_index = i
                break
    if footer_index <= header_index+1:
        return
    sheet = QWidget()
    sheet.setObjectName('SettingsSheet')
    interior = QVBoxLayout(sheet)
    interior.setContentsMargins(18, 16, 18, 16)
    interior.setSpacing(12)
    for _ in range(footer_index-header_index-1):
        index = header_index+1
        stretch = body.stretch(index)
        item = body.takeAt(index)
        if item.widget() is not None:
            interior.addWidget(item.widget(), stretch, item.alignment())
        elif item.layout() is not None:
            layout=item.layout();layout.setParent(None)
            interior.addLayout(layout, stretch)
        else:
            interior.addItem(item)
    if dialog.findChildren(QFormLayout) and not dialog.findChildren(QScrollArea):
        # Short windows must scroll the form, never squeeze labels and editors
        # into overlapping rows. Lists and existing tabbed scroll panes keep
        # their own scrolling behavior.
        frame=QWidget();frame.setObjectName('SettingsSheet')
        frame_layout=QVBoxLayout(frame);frame_layout.setContentsMargins(8,8,8,8)
        scroll=QScrollArea();scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidgetResizable(True);scroll.setMinimumSize(0,0)
        sheet.setObjectName('SettingsContents');scroll.setWidget(sheet)
        frame_layout.addWidget(scroll)
        body.insertWidget(header_index+1,frame,1)
    else:
        body.insertWidget(header_index+1, sheet, 1)


def finish_dialog(dialog):
    if dialog.objectName()=='SettingsDialog':
        return
    # Share the saved display density without coupling the popup constructors.
    queue=[dialog];seen=set();cfg=None
    while queue:
        obj=queue.pop(0)
        if id(obj) in seen:continue
        seen.add(id(obj))
        candidate=getattr(obj,'cfg',None)
        if isinstance(candidate,dict):cfg=candidate;break
        for name in ('dock','tray','runtime','manager','importer','clock','note','panel','owner'):
            child=getattr(obj,name,None)
            if child is not None and not callable(child):queue.append(child)
    from settings_layout import fit_auxiliary_dialog
    fit_auxiliary_dialog(dialog,cfg or {})


def stylesheet(colors):
    c = dict(colors)
    c['frame'] = '#f0f5f8' if QColor(c['ground']).lightness()>128 else '#1c2227'
    return '''
    QDialog[designPopup="true"] {background:%(frame)s; border:1px solid %(line)s;}
    QWidget#SettingsSheet, QStackedWidget#SettingsSheet {background:%(surface)s; border:1px solid %(line)s; border-radius:16px;}
    QWidget#SettingsSheet QScrollArea, QWidget#SettingsSheet QScrollArea > QWidget > QWidget,
    QStackedWidget#SettingsSheet QScrollArea, QStackedWidget#SettingsSheet QScrollArea > QWidget > QWidget {background:%(surface)s; border:0;}
    QWidget#SettingsField {background:transparent; border:0;}
    QLabel[role="field-label"] {font-weight:500;}
    QLabel[role="section"] {font-size:15px; font-weight:600; padding-top:8px;}
    QDialog[designPopup="true"] QLabel[role="title"] {font-size:18px; font-weight:600;}
    QDialog[designPopup="true"] QLabel[role="page-title"] {font-size:20px; font-weight:600; padding-bottom:6px;}
    QDialog[designPopup="true"] QPushButton, QDialog[designPopup="true"] QLineEdit,
    QDialog[designPopup="true"] QComboBox, QDialog[designPopup="true"] QSpinBox {border-radius:6px;}
    QDialog[designPopup="true"] QTabBar::tab {padding:9px 12px;}
    QDialog[designPopup="true"] QListWidget#SettingsNav::item {padding:8px 10px; height:26px; min-height:26px; border-radius:8px;}
    QDialog[designPopup="true"] QSlider {background:transparent; border:0; padding:0; min-height:22px;}
    QDialog[designPopup="true"] QSlider::groove:horizontal {height:5px; background:%(hover)s; border-radius:2px;}
    QDialog[designPopup="true"] QSlider::sub-page:horizontal {background:#438aa7; border-radius:2px;}
    QDialog[designPopup="true"] QSlider::handle:horizontal {background:#438aa7; border:0; width:12px; margin:-4px 0; border-radius:6px;}
    QDialog[designPopup="true"] QSlider:focus::handle:horizontal {border:1px solid %(text)s;}
    QDialog[designPopup="true"] QTreeWidget {background:%(surface)s; color:%(text)s; border:0; padding:4px;}
    QDialog[designPopup="true"] QTreeWidget::item {padding:8px 6px; border-radius:6px;}
    QDialog[designPopup="true"] QTreeWidget::item:selected {background:%(selection)s;}
    QDialog[designPopup="true"] QPlainTextEdit {padding:8px; border-radius:6px;}
    ''' % c
