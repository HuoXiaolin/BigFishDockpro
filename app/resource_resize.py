"""Thin native edge handles; resize one panel and persist on release."""
from PyQt5.QtCore import Qt,QRect
from PyQt5.QtWidgets import QWidget,QApplication
from screen_layout import capture,screen_records


class ResizeEdge(QWidget):
    def __init__(self,owner,edge):
        super().__init__(owner);self.owner=owner;self.edge=edge;self.active=False
        self.setCursor(Qt.SizeFDiagCursor if edge in ('lt','rb') else Qt.SizeBDiagCursor if edge in ('rt','lb') else Qt.SizeHorCursor if edge in ('l','r') else Qt.SizeVerCursor)
        self.setAccessibleName('拖动调整胶囊大小');self.setMouseTracking(True)
    def mousePressEvent(self,event):
        if event.button()!=Qt.LeftButton:return
        w=self.owner;self.active=True;self.start=event.globalPos();self.original=QRect(w.geometry())
        w.liquid.snap.stop();w.liquid.landing=False;w.liquid.stop_bridge()
        screen=QApplication.screenAt(w.geometry().center()) or QApplication.primaryScreen();self.area=screen.availableGeometry()
        w.press=self.start;w.enter_timer.stop();event.accept()
    def mouseMoveEvent(self,event):
        if not self.active:return
        w=self.owner;compact=w.service.compact;delta=event.globalPos()-self.start;r=QRect(self.original)
        min_w,min_h,max_w,max_h=(96,28,1400,100) if compact else (260,180,1000,800)
        min_w=min(min_w,self.area.width());min_h=min(min_h,self.area.height())
        if 'l' in self.edge:r.setLeft(max(self.area.left(),min(r.right()-min_w+1,max(r.right()-max_w+1,r.left()+delta.x()))))
        if 'r' in self.edge:r.setRight(min(self.area.right(),max(r.left()+min_w-1,min(r.left()+max_w-1,r.right()+delta.x()))))
        if 't' in self.edge:r.setTop(max(self.area.top(),min(r.bottom()-min_h+1,max(r.bottom()-max_h+1,r.top()+delta.y()))))
        if 'b' in self.edge:r.setBottom(min(self.area.bottom(),max(r.top()+min_h-1,min(r.top()+max_h-1,r.bottom()+delta.y()))))
        w.setGeometry(r);event.accept()
    def mouseReleaseEvent(self,event):
        if event.button()!=Qt.LeftButton or not self.active:return
        self.mouseMoveEvent(event);self.active=False;w=self.owner;w.press=None;r=QRect(w.geometry())
        if w.service.compact:
            changes=dict(resource_compact_width=r.width(),resource_compact_height=r.height(),resource_compact_auto_width=False)
        else:
            changes=dict(resource_expanded_width=r.width(),resource_expanded_height=r.height())
        if w.taskbar_slot() is None:
            changes['resource_layout']=capture(list(r.getRect()),screen_records())
            # A deliberate resize keeps the dragged edge where it was released.
            changes['resource_edge']='free'
        if not w.service.set_options(**changes):w.reposition()
        if w.taskbar_placement:w.taskbar_placement.resume()
        event.accept()


class ResizeEdges:
    def __init__(self,owner):
        self.owner=owner;self.handles={edge:ResizeEdge(owner,edge) for edge in ('l','r','t','b','lt','rt','lb','rb')}
    def sync(self):
        w=self.owner;width,height=w.width(),w.height();corner=12;edge=5
        boxes={'l':(0,corner,edge,height-2*corner),'r':(width-edge,corner,edge,height-2*corner),
               't':(corner,0,width-2*corner,edge),'b':(corner,height-edge,width-2*corner,edge),
               'lt':(0,0,corner,corner),'rt':(width-corner,0,corner,corner),
               'lb':(0,height-corner,corner,corner),'rb':(width-corner,height-corner,corner,corner)}
        show=not w.service.compact or (w.service.cfg['resource_fold']!='ball' and w.taskbar_slot() is None)
        for key,handle in self.handles.items():
            handle.setGeometry(*boxes[key]);handle.setVisible(show);handle.raise_()
