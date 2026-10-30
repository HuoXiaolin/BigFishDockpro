"""Adaptive settings-window density, based on immutable compact-layout metrics."""
from PyQt5.QtCore import Qt,QTimer
from PyQt5.QtWidgets import QApplication,QWidget
from ui_style import ModernComboBox,label,density_stylesheet

MODES=[('自动适配','auto'),('小','small'),('中','medium'),('大','large'),('手动调整','custom')]


def automatic_mode(area):
    return 'large' if area.width()>=3000 or area.height()>=1700 else 'medium' if area.width()>=1550 and area.height()>=850 else 'small'


class SettingsSizingMixin:
    def create_size_selector(self):
        self._interface_ready=False;self._interface_resizing=False;self._custom_density=100;self._manual_dimensions=[]
        self.size_mode=ModernComboBox()
        for title,key in MODES:self.size_mode.addItem(title,key)
        self.size_mode.setFixedWidth(132);self.size_mode.setAccessibleName('设置窗口大小')
        from PyQt5.QtWidgets import QHBoxLayout
        selector=QWidget();row=QHBoxLayout(selector);row.setContentsMargins(0,0,0,0);row.setSpacing(8)
        row.addWidget(label('界面尺寸'));row.addWidget(self.size_mode)
        self.header.layout().insertWidget(self.header.layout().count()-2,selector)
        self.fields['settings_size']=self.size_mode
    def initialize_size_behavior(self):
        self._density_reference=[]
        from PyQt5 import sip
        def visit_layout(layout):
            margins=layout.contentsMargins();row=[layout,[value/.7 for value in (margins.left(),margins.top(),margins.right(),margins.bottom())],layout.spacing()/.7 if layout.spacing()>=0 else None,None,None]
            if hasattr(layout,'horizontalSpacing'):
                row[3]=layout.horizontalSpacing()/.7 if layout.horizontalSpacing()>=0 else None;row[4]=layout.verticalSpacing()/.7 if layout.verticalSpacing()>=0 else None
            self._density_reference.append(('layout',row))
            for index in range(layout.count()):
                child=layout.itemAt(index).layout()
                if child is not None:visit_layout(child)
        for widget in [self]+self.findChildren(QWidget):
            if widget.window() is not self:continue
            for axis in ('Width','Height'):
                minimum=getattr(widget,'minimum'+axis)();maximum=getattr(widget,'maximum'+axis)()
                if minimum==maximum and maximum<16777215:self._density_reference.append(('fixed',(widget,axis,minimum/.7)))
            if widget.layout():visit_layout(widget.layout())
        self._interface_ready=True;self._custom_density=self.tray.cfg.get('settings_custom_density',100);self._manual_dimensions=list(self.tray.cfg.get('settings_manual_size',[]))
        self.size_mode.setCurrentIndex(max(0,self.size_mode.findData(self.tray.cfg.get('settings_size','auto'))))
        self.size_mode.currentIndexChanged.connect(self.adapt_interface);self.adapt_interface()
    def available_interface_area(self):
        screen=QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        return screen.availableGeometry()
    def refresh_interface_style(self):
        if not getattr(self,'_interface_ready',False):return
        from PyQt5 import sip
        factor=float(self.property('interfaceScale') or .7)
        self._interface_resizing=True
        try:
            base=getattr(QApplication.instance(),'_base_stylesheet','')
            if base:self.setStyleSheet(density_stylesheet(base,factor))
            for kind,record in self._density_reference:
                if kind=='fixed':
                    widget,axis,value=record
                    if not sip.isdeleted(widget):getattr(widget,'setFixed'+axis)(max(1,round(value*factor)))
                else:
                    layout,margins,spacing,horizontal,vertical=record
                    if sip.isdeleted(layout):continue
                    layout.setContentsMargins(*(round(value*factor) for value in margins))
                    if spacing is not None:layout.setSpacing(round(spacing*factor))
                    if horizontal is not None:layout.setHorizontalSpacing(round(horizontal*factor))
                    if vertical is not None:layout.setVerticalSpacing(round(vertical*factor))
            area=self.available_interface_area();self.setMinimumSize(min(round(640*factor),area.width()-24),min(round(480*factor),area.height()-24))
        finally:self._interface_resizing=False
    def adapt_interface(self,*args):
        if not getattr(self,'_interface_ready',False):return
        mode=self.size_mode.currentData() or 'auto';area=self.available_interface_area()
        selected=automatic_mode(area) if mode=='auto' else mode
        factor={'small':.7,'medium':1.0,'large':1.5}.get(selected,self._custom_density/100)
        self._interface_resizing=True
        self.setProperty('interfaceScale',factor);self.refresh_interface_style();self._interface_resizing=True
        try:
            target=self._manual_dimensions if mode=='custom' and len(self._manual_dimensions)==2 else [round(800*factor),round(640*factor)]
            width=min(target[0],max(300,area.width()-24));height=min(target[1],max(250,area.height()-24));self.resize(width,height)
            self.move(max(area.left(),min(self.x(),area.right()-self.width()+1)),max(area.top(),min(self.y(),area.bottom()-self.height()+1)))
        finally:self._interface_resizing=False
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if getattr(self,'_interface_ready',False) and not self._interface_resizing and self.isVisible() and event.oldSize().isValid():
            self._manual_dimensions=[self.width(),self.height()];self._custom_density=round(float(self.property('interfaceScale') or .7)*100)
            blocked=self.size_mode.blockSignals(True);self.size_mode.setCurrentIndex(self.size_mode.findData('custom'));self.size_mode.blockSignals(blocked)
    def showEvent(self,event):
        super().showEvent(event)
        handle=self.windowHandle()
        if handle and not getattr(self,'_bound_settings_screen',False):
            self._bound_settings_screen=True;handle.screenChanged.connect(lambda *_:QTimer.singleShot(0,self._adapt_if_auto))
    def _adapt_if_auto(self):
        if self.size_mode.currentData()=='auto':self.adapt_interface()


def fit_auxiliary_dialog(dialog,cfg):
    """New card controls inherit the saved settings density on their current screen."""
    if dialog.property('auxiliaryDensityApplied'):return
    dialog.setProperty('auxiliaryDensityApplied',True)
    screen=QApplication.screenAt(dialog.frameGeometry().center()) or QApplication.primaryScreen();area=screen.availableGeometry()
    mode=cfg.get('settings_size','auto');selected=automatic_mode(area) if mode=='auto' else mode
    factor={'small':.7,'medium':1.0,'large':1.5}.get(selected,cfg.get('settings_custom_density',100)/100)
    ratio=factor/.7;size=dialog.size();minimum=dialog.minimumSize();dialog.setProperty('interfaceScale',factor)
    def layout_scale(layout):
        margins=layout.contentsMargins();layout.setContentsMargins(*(round(value*ratio) for value in (margins.left(),margins.top(),margins.right(),margins.bottom())))
        if layout.spacing()>=0:layout.setSpacing(round(layout.spacing()*ratio))
        if hasattr(layout,'horizontalSpacing'):
            for name in ('HorizontalSpacing','VerticalSpacing'):
                value=getattr(layout,name[0].lower()+name[1:])()
                if value>=0:getattr(layout,'set'+name)(round(value*ratio))
        for i in range(layout.count()):
            child=layout.itemAt(i).layout()
            if child is not None:layout_scale(child)
    for widget in [dialog]+dialog.findChildren(QWidget):
        if widget.window() is not dialog:continue
        for axis in ('Width','Height'):
            low=getattr(widget,'minimum'+axis)();high=getattr(widget,'maximum'+axis)()
            if low==high and high<16777215:getattr(widget,'setFixed'+axis)(round(low*ratio))
        if widget.layout():layout_scale(widget.layout())
    base=getattr(QApplication.instance(),'_base_stylesheet','')
    if base:dialog.setStyleSheet(density_stylesheet(base,factor))
    dialog.setMinimumSize(min(round(minimum.width()*ratio),area.width()-24),min(round(minimum.height()*ratio),area.height()-24))
    dialog.resize(min(round(size.width()*ratio),area.width()-24),min(round(size.height()*ratio),area.height()-24))
