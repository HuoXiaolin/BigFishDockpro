"""Per-card/group/note folding and centered geometry, independent of shared colors."""
import copy
from PyQt5.QtCore import Qt,QPoint,QRect
from PyQt5.QtGui import QIcon,QPainter,QPalette
from PyQt5.QtWidgets import QDialog,QVBoxLayout,QFormLayout,QHBoxLayout,QToolButton,QApplication
from ui_style import SettingsHeader,ModernComboBox,ModernSpinBox,button,label,compact_dialog


def normalize(value):
    if not isinstance(value,dict):return {}
    style=value.get('style','capsule');ratio=value.get('ratio',70)
    return {'style':style if style in ('bar','capsule','ball') else 'capsule','ratio':max(1,min(100,ratio)) if type(ratio) is int else 70}


def settings(window):
    if hasattr(window,'model'):
        cfg=window.dock.cfg;default={'style':cfg['panel_collapse_style'],'ratio':cfg['panel_capsule_ratio']}
        row=next((g for g in cfg['merge_groups'] if g['id']==window.manager.group_id(window.identity)),{}) if window.manager.is_merged(window.identity) else window.model
    else:default={'style':'bar','ratio':100};row=window.row()
    return normalize(row.get('fold')) or default


def geometry(expanded,options,height):
    x,y,w,h=expanded
    width=w if options['style']=='bar' else height if options['style']=='ball' else max(height,round(w*options['ratio']/100))
    width=min(w,width)
    return [x+round((w-width)/2),y,width,height] if options['style']!='bar' else [x,y,width,height]


class Badge(QToolButton):
    def __init__(self,owner):
        super().__init__(owner);self.owner=owner;self.origin=None;self.moved=False
        self.setStyleSheet('QToolButton {background:transparent;border:0;padding:0;}');self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.setContextMenuPolicy(Qt.CustomContextMenu);self.customContextMenuRequested.connect(self.menu)
    def paintEvent(self,event):
        painter=QPainter(self);size=min(round(22*self.owner.ui_factor),self.height()-12,self.width()-12)
        self.icon().paint(painter,QRect((self.width()-size)//2,(self.height()-size)//2,size,size))
    def menu(self,point):
        menu=self.owner.build_panel_menu() if hasattr(self.owner,'model') else self.owner.build_menu()
        menu.exec_(self.mapToGlobal(point));menu.deleteLater()
    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:self.origin=event.globalPos()-self.owner.pos();self.start=event.globalPos();self.moved=False;event.accept()
        else:super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if self.origin is not None and not (self.owner.option('locked') if hasattr(self.owner,'model') else self.owner.row()['locked']):
            if (event.globalPos()-self.start).manhattanLength()>QApplication.startDragDistance():self.moved=True
            if self.moved:self.owner.move(event.globalPos()-self.origin)
    def mouseReleaseEvent(self,event):
        if event.button()==Qt.LeftButton and self.origin is not None:
            self.origin=None
            if self.moved:self.owner.store_geometry() if hasattr(self.owner,'model') else self.owner.save_geometry()
            elif hasattr(self.owner,'model'):self.owner.expand()
            else:self.owner.set_collapsed(False)
        else:super().mouseReleaseEvent(event)


def header(window,collapsed):
    compact=collapsed and (settings(window)['style']!='bar' or window.width()<round(240*window.ui_factor))
    if hasattr(window,'model'):
        controls=[window.header_icon,window.title,window.count,window.settings_button,window.menu_button,window.collapse_button];pixmap=window.header_icon.pixmap();title=window.model['name']
    else:
        controls=[window.handle,window.title,window.flip_button,window.settings_button,window.more,window.collapse_button];pixmap=window.handle.pixmap();title=window.row()['title']
    for control in controls:control.setVisible(not compact)
    badge=getattr(window,'fold_badge',None)
    if badge is None:badge=window.fold_badge=Badge(window)
    badge.setVisible(compact)
    if compact:
        badge.setFont(window.title.font());badge.setPalette(window.title.palette());badge.setGeometry(window.rect());badge.setIcon(QIcon(pixmap) if pixmap else QIcon());badge.setText('');badge.setToolTip(title+' · 点击展开，右键设置，拖动移动');badge.raise_()


def note_geometry(window,collapsed):
    options=settings(window);expanded=getattr(window,'_fold_expanded',list(window.geometry().getRect()))
    window.setMinimumSize(1,1);window.setMaximumSize(16777215,16777215)
    if collapsed:
        target=geometry(expanded,options,max(30,round(42*window.ui_factor)));window.setFixedSize(target[2],target[3]);window.move(*target[:2]);window._fold_offset=(target[0]-expanded[0],target[1]-expanded[1])
    elif getattr(window,'_fold_was_collapsed',False):window.setGeometry(*expanded)
    else:window._fold_expanded=list(window.geometry().getRect())
    if not collapsed:window.setMinimumSize(max(160,round(230*min(1,window.ui_factor))),max(96,round(150*min(1,window.ui_factor))))
    if window.row()['locked']:window.setFixedSize(window.size())
    window.fit_title();window._fold_was_collapsed=collapsed
    header(window,collapsed)
    if collapsed:apply_compact_size(window,target);header(window,collapsed)


class FoldOptions(QDialog):
    def __init__(self,owner):
        super().__init__(owner,Qt.Window|Qt.FramelessWindowHint|Qt.WindowMinimizeButtonHint);self.owner=owner;self.setWindowTitle('收起样式');self.resize(410,230)
        body=QVBoxLayout(self);body.addWidget(SettingsHeader(self,'收起样式'));form=QFormLayout();body.addLayout(form)
        self.style=ModernComboBox()
        for title,key in [('方条','bar'),('胶囊','capsule'),('圆球','ball')]:self.style.addItem(title,key)
        self.ratio=ModernSpinBox();self.ratio.setRange(1,100);form.addRow('收起形状',self.style);form.addRow('胶囊宽度（%）',self.ratio)
        value=settings(owner);self.style.setCurrentIndex(self.style.findData(value['style']));self.ratio.setValue(value['ratio'])
        self.status=label('只修改当前独立卡片、合并组或便签。胶囊宽度最低为圆球直径。','muted');self.status.setWordWrap(True);body.addWidget(self.status)
        row=QHBoxLayout();row.addStretch();row.addWidget(button('关闭',self.reject));row.addWidget(button('保存',self.commit,'primary'));body.addLayout(row);compact_dialog(self)
    def commit(self):
        owner=self.owner;value={'style':self.style.currentData(),'ratio':self.ratio.value()}
        if hasattr(owner,'model'):success=owner.manager.update_panel(owner.identity,fold=value)
        else:success=owner.manager.update_and_save(owner.identity,fold=value)
        if success:
            if hasattr(owner,'model'):owner.set_collapsed_geometry(owner.collapsed)
            else:owner.apply_style()
            self.status.setText('收起样式已保存。')
        else:self.status.setText('保存失败，原设置保留。')


def native_minimum(window,message):
    # Windows retains a caption-sized tracking minimum on frameless tool windows.
    import ctypes
    from ctypes import wintypes
    msg=ctypes.cast(int(message),ctypes.POINTER(wintypes.MSG)).contents
    collapsed=window.collapsed if hasattr(window,'model') else window.row().get('collapsed',False)
    if msg.message!=0x24 or not collapsed:return False
    class MinMax(ctypes.Structure):
        _fields_=[(name,wintypes.POINT) for name in ('reserved','max_size','max_position','min_track','max_track')]
    limits=ctypes.cast(msg.lParam,ctypes.POINTER(MinMax)).contents
    limits.min_track.x=1;limits.min_track.y=1
    return True


def apply_compact_size(window,target):
    # Enforce the requested client rectangle after Qt's Windows tool-window hint.
    import ctypes
    from ctypes import wintypes
    window.setFixedSize(target[2],target[3]);window.move(*target[:2])
    user=ctypes.windll.user32
    user.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
    ratio=window.devicePixelRatioF()
    user.SetWindowPos(int(window.winId()),None,0,0,round(target[2]*ratio),round(target[3]*ratio),0x16)
