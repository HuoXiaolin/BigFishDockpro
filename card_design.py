"""Light card compositions inspired by Uiverse, colored by this app's accent."""
from PyQt5.QtCore import Qt,QPointF,QRectF
from PyQt5.QtGui import QColor,QLinearGradient,QPen,QPainterPath
DESIGNS=[('极光玻璃','aurora'),('浅色渐变','gradient'),('柔和纸卡','paper'),('极简大字','minimal')]


def accent_color(cfg):return QColor(cfg.get('theme_color') or cfg.get('panel_color') or '#b8d9ef')


def blend(left,right,amount):
    return QColor(*(round(a*(1-amount)+b*amount) for a,b in zip(left.getRgb()[:3],right.getRgb()[:3])))


def paint_design(painter,rect,cfg,design=None,clear=False,body_top=None,body_inset=4,corner_radius=None):
    if clear:return
    design=design if design and design!='follow' else cfg.get('card_design','aurora')
    accent=accent_color(cfg);white=QColor('#ffffff');painter.save();painter.setRenderHint(painter.Antialiasing)
    radius=min(20,rect.height()*.12) if corner_radius is None else corner_radius
    path=QPainterPath();path.addRoundedRect(rect,radius,radius)
    painter.setClipPath(path,Qt.IntersectClip)
    if design=='aurora':
        wash=QLinearGradient(rect.topLeft(),rect.bottomRight());a=QColor(accent);a.setAlpha(28);b=QColor('#ffffff');b.setAlpha(8)
        wash.setColorAt(0,a);wash.setColorAt(.55,b);wash.setColorAt(1,a);painter.fillPath(path,wash)
    elif design=='gradient':
        fill=QLinearGradient(rect.topLeft(),rect.bottomRight());fill.setColorAt(0,blend(white,accent,.62));fill.setColorAt(.45,blend(white,accent,.22));fill.setColorAt(1,blend(white,accent,.55));painter.fillPath(path,fill)
        # Collection headers vary with tab visibility, font size and screen scale.
        # A supplied boundary is in widget coordinates, matching rect coordinates.
        if body_top is None:body_top=rect.top()+min(43,rect.height()*.23)
        if body_top<rect.bottom()-body_inset:
            inset=QRectF(rect.left()+body_inset,body_top,rect.width()-2*body_inset,rect.bottom()-body_inset-body_top)
            inside=QPainterPath();inside.addRoundedRect(inset,max(4,radius-3),max(4,radius-3));painter.fillPath(inside,blend(white,accent,.07))
    elif design=='paper':
        cream=QColor('#fff8eb');fill=QLinearGradient(rect.topLeft(),rect.bottomRight());fill.setColorAt(0,cream);fill.setColorAt(1,blend(cream,accent,.08));painter.fillPath(path,fill)
        stroke=QColor(accent);stroke.setAlpha(105);painter.setPen(QPen(stroke,1));painter.drawLine(QPointF(rect.left()+14,rect.top()+38),QPointF(rect.right()-14,rect.top()+38))
    else:
        color=blend(white,accent,.035);color.setAlpha(242);painter.fillPath(path,color)
    edge=QLinearGradient(rect.topLeft(),rect.bottomRight());edge.setColorAt(0,blend(white,accent,.55));edge.setColorAt(.48,blend(white,accent,.18));edge.setColorAt(1,blend(white,accent,.65))
    painter.setBrush(Qt.NoBrush);painter.setPen(QPen(edge,1.4 if design=='aurora' else 1));painter.drawPath(path);painter.restore()
