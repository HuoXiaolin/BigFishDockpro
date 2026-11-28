"""Map capsule content coordinates to the native window, independently of screen DPI."""
from weakref import ref
from PyQt5.QtCore import QPoint, QRectF, QSize, Qt
from PyQt5.QtGui import QPainter, QTransform
from PyQt5.QtWidgets import QFrame, QGraphicsScene, QGraphicsView


def content_scale(window):
    return window.service.cfg.get('resource_content_scale', 100) / 100


def content_size(window):
    scale = content_scale(window)
    return QSize(max(1, round(window.width() / scale)), max(1, round(window.height() / scale)))


def window_rect(window, rect):
    scale = content_scale(window)
    return QRectF(rect.x()*scale, rect.y()*scale, rect.width()*scale, rect.height()*scale)


def native_host(widget):
    root=widget.window()
    owner=getattr(root,'capsule_owner',None)
    return owner() if owner and owner() is not None else root


def widget_rect(owner, child, rect):
    area=QRectF(rect)
    view=getattr(owner,'scaled_detail',None)
    if view and child.window() is owner.detail:
        area.translate(child.mapTo(owner.detail,QPoint()))
        area=view.viewportTransform().mapRect(area)
        area.translate(view.viewport().mapTo(owner,QPoint()))
    else:
        area.translate(child.mapTo(owner,QPoint()))
    return area


class ScaledDetailView(QGraphicsView):
    """Use Qt's native event mapping for the live controls and custom-painted pages."""

    def __init__(self, owner):
        super().__init__(owner)
        scene = QGraphicsScene(self)
        self.setScene(scene)
        self.setFrameShape(QFrame.NoFrame)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.setResizeAnchor(QGraphicsView.NoAnchor)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet('QGraphicsView { background: transparent; border: 0; }')
        self.viewport().setAutoFillBackground(False)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        detail = owner.detail
        detail.capsule_owner=ref(owner)
        detail.setParent(None)
        detail.setStyleSheet(owner.styleSheet())
        detail.setPalette(owner.palette())
        self.proxy = scene.addWidget(detail)
        self.proxy.setPos(0, 0)

    def fit_content(self, bounds, scale):
        if self.geometry() != bounds:
            self.setGeometry(bounds)
        if self.transform().m11() != scale:
            self.setTransform(QTransform.fromScale(scale, scale))
        detail = self.proxy.widget()
        width = max(1, int(bounds.width()/scale), detail.minimumSizeHint().width())
        bar = self.horizontalScrollBar().sizeHint().height() if width*scale > bounds.width() else 0
        detail.resize(width, max(1, int((bounds.height()-bar)/scale)))
        self.setSceneRect(self.proxy.geometry())

    def release(self, owner):
        detail = self.proxy.widget()
        self.proxy.setWidget(None)
        detail.setParent(owner)
        detail.setStyleSheet('')
        detail.setPalette(owner.palette())
        self.hide()
        self.deleteLater()
