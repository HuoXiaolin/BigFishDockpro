"""Native test events without bundling QtTest into the shipped application."""
from PyQt5.QtCore import Qt,QEvent,QEventLoop,QPointF,QTimer
from PyQt5.QtGui import QKeyEvent,QMouseEvent
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
    def drag(widget,point,delta):
        start=widget.mapToGlobal(point);end=start+delta
        for kind,position,button,buttons in (
            (QEvent.MouseButtonPress,start,Qt.LeftButton,Qt.LeftButton),
            (QEvent.MouseMove,end,Qt.NoButton,Qt.LeftButton),
            (QEvent.MouseButtonRelease,end,Qt.LeftButton,Qt.NoButton),
        ):
            local=widget.mapFromGlobal(position)
            QApplication.sendEvent(widget,QMouseEvent(kind,QPointF(local),QPointF(position),button,buttons,Qt.NoModifier))
