"""Native test events without bundling QtTest into the shipped application."""
from PyQt5.QtCore import Qt,QEvent,QEventLoop,QTimer
from PyQt5.QtGui import QKeyEvent
from PyQt5.QtWidgets import QApplication

class Events:
    @staticmethod
    def qWait(milliseconds):
        loop=QEventLoop();QTimer.singleShot(milliseconds,loop.quit);loop.exec_()
    @staticmethod
    def keyClick(widget,key,modifier=Qt.NoModifier):
        for kind in (QEvent.KeyPress,QEvent.KeyRelease):
            QApplication.sendEvent(widget,QKeyEvent(kind,key,modifier))
