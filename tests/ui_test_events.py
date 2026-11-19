"""Native test events without bundling QtTest into the shipped application."""
from PyQt5.QtCore import Qt,QEvent,QEventLoop,QPoint,QPointF,QTimer
from PyQt5.QtGui import QKeyEvent,QMouseEvent,QWheelEvent
from PyQt5.QtWidgets import QApplication

class Events:
    @staticmethod
    def qWait(milliseconds):
        loop=QEventLoop();QTimer.singleShot(milliseconds,loop.quit);loop.exec_()
    @staticmethod
    def keyClick(widget,key,modifier=Qt.NoModifier):
        for kind in (QEvent.KeyPress,QEvent.KeyRelease):
            QApplication.sendEvent(widget,QKeyEvent(kind,key,modifier))
    @staticmethod
    def wheel(widget, delta):
        center = widget.rect().center()
        event = QWheelEvent(QPointF(center), QPointF(widget.mapToGlobal(center)),
                            QPoint(), QPoint(0, delta), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
        event.ignore()
        QApplication.sendEvent(widget, event)
        return event.isAccepted()
    @staticmethod
    def drag(widget,point,delta):
        start=widget.mapToGlobal(point);end=start+delta
        for kind,position,button,buttons in (
            (QEvent.MouseButtonPress,start,Qt.LeftButton,Qt.LeftButton),
            (QEvent.MouseMove,end,Qt.NoButton,Qt.LeftButton),
            (QEvent.MouseButtonRelease,end,Qt.LeftButton,Qt.NoButton),
        ):
            local=widget.mapFromGlobal(position)
            QApplication.sendEvent(widget,QMouseEvent(kind,QPointF(local),QPointF(position),button,buttons,Qt.NoModifier))


def check_edge_resize(widget, *, locked=False):
    """Exercise each real edge target, including the four diagonals."""
    for horizontal,vertical in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
        before=widget.geometry()
        rect=widget.rect()
        x=rect.left()+2 if horizontal<0 else rect.right()-2 if horizontal>0 else rect.center().x()
        y=rect.top()+2 if vertical<0 else rect.bottom()-2 if vertical>0 else rect.center().y()
        point=QPoint(x,y)
        assert widget.childAt(point) is None, point
        step=QPoint(horizontal*8,vertical*6)
        Events.drag(widget,point,step)
        after=widget.geometry()
        if locked:
            assert after==before
            continue
        assert after.getRect()==(before.x()+min(0,step.x()),before.y()+min(0,step.y()),
                                 before.width()+abs(step.x()),before.height()+abs(step.y())), (point,before,after)
