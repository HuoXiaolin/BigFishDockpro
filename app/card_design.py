"""Light card compositions inspired by Uiverse, colored by this app's accent."""
from PyQt5.QtCore import Qt,QPointF,QRectF
from PyQt5.QtGui import QBrush,QColor,QGradient,QLinearGradient,QPen,QPainterPath
from appearance_presets import THEME_GRADIENTS
DESIGNS=[('液态玻璃','aurora'),('浅色渐变','gradient'),('经典纸张','paper'),('极简纯色','minimal'),('清透水晶','crystal'),('柔光流彩','flowing'),('活力原色','vivid'),('浅色纸玻璃','paper_glass')]

# Card surfaces, in light and dark order.
SOFT_SURFACES={
    'sky':('#dbe9f3','#32465a'),
    'lavender':('#e7e8f8','#31364f'),
    'mint':('#dceee5','#233e36'),
    'peach':('#f9e7dc','#443631'),
    'rose':('#eac9dd','#503249'),
}

CAPSULE_GRADIENTS={
    'sky':THEME_GRADIENTS['liquid'],
    'lavender':THEME_GRADIENTS['vivid'],
    'mint':THEME_GRADIENTS['clear'],
    'peach':('#ffcf1b','#ff8818'),
    'rose':('#f869d5','#5650de'),
    'ice':('#6ee2f5','#6454f0'),
}

# Hue strength and opacity for the surface laid over the parent material.
SURFACE_MATERIALS={
    'clear':(.72,239),
    'solid':(.88,255),
    'plain':(.84,255),
    'paper':(.77,255),
    'paper_glass':(.77,249),
    'mica':(.76,248),
    'acrylic':(.82,243),
    'crystal':(.82,240),
    'flowing':(.84,242),
}


def accent_color(cfg):return QColor(cfg.get('theme_color') or cfg.get('panel_color') or '#b8d9ef')


def blend(left,right,amount):
    return QColor(*(round(a*(1-amount)+b*amount) for a,b in zip(left.getRgb()[:3],right.getRgb()[:3])))


def soft_surface(tone,light,appearance):
    material=appearance.get('material','liquid')
    strength,opacity=SURFACE_MATERIALS.get(material,(.86,241))
    base=QColor('#f5f7fa' if light else '#282d34')
    accent=QColor(appearance.get('color') or '')
    if accent.isValid():
        base=blend(base,accent,.23 if material in ('solid','plain','paper','paper_glass') else .14)
    color=blend(base,QColor(SOFT_SURFACES[tone][0 if light else 1]),strength)
    if opacity<255:opacity=min(253,opacity+round(appearance.get('opacity',0)*.05))
    color.setAlpha(opacity)
    return color


def capsule_card_brush(tone,light,appearance,*,alpha,base=None,active=False):
    strength,_=SURFACE_MATERIALS.get(appearance['material'],(.86,241))
    if base is None:
        base=QColor('#f9fbfd' if light else '#1a212d')
        tint=QColor(appearance['color'])
        if tint.isValid():base=blend(base,tint,.10 if light else .07)
        strength*=.30 if light else .24
    else:
        base=QColor(base)
        strength*=.16
    if active:base=blend(base,QColor('#c7d4e4' if light else '#52627b'),.24)
    gradient=QLinearGradient(0,0,1,1)
    gradient.setCoordinateMode(QGradient.ObjectBoundingMode)
    for position,value in enumerate(CAPSULE_GRADIENTS[tone]):
        color=blend(base,QColor(value),strength)
        color.setAlpha(alpha)
        gradient.setColorAt(position,color)
    return QBrush(gradient)


def paint_capsule_card(painter,rect,colors,tone,appearance,*,radius=9,base=None,active=False,focused=False):
    light=colors['light']
    edge=QColor(colors['muted'] if focused else colors['ink'])
    if not focused:edge.setAlpha(23 if light else 37)
    painter.setPen(QPen(edge,1))
    painter.setBrush(capsule_card_brush(tone,light,appearance,alpha=colors['card_alpha'],base=base,active=active))
    painter.drawRoundedRect(rect.adjusted(.5,.5,-.5,-.5),radius,radius)


def paint_design(painter,rect,cfg,design=None,clear=False,body_top=None,body_inset=4,corner_radius=None,header_separator=True):
    if clear:return
    design=design if design and design!='follow' else cfg.get('card_design','aurora')
    accent=accent_color(cfg);white=QColor('#ffffff');painter.save();painter.setRenderHint(painter.Antialiasing)
    radius=min(20,rect.height()*.12) if corner_radius is None else corner_radius
    path=QPainterPath();path.addRoundedRect(rect,radius,radius)
    painter.save();painter.setClipPath(path,Qt.IntersectClip)
    if design in ('crystal','flowing','paper_glass'):
        # The shared material already owns the edge and wallpaper surface. Keep
        # content still; only the header receives a small readable tone step.
        boundary = body_top if body_top is not None else rect.top()+min(40,rect.height()*.22)
        if header_separator and boundary < rect.bottom()-2:
            header=QColor('#ffffff');header.setAlpha(22 if design!='paper_glass' else 46)
            painter.fillRect(QRectF(rect.left(),rect.top(),rect.width(),max(0,boundary-rect.top())),header)
        painter.restore();painter.restore();return
    if design=='vivid':
        wash=QLinearGradient(rect.topLeft(),rect.topRight())
        for stop,rgb in enumerate(THEME_GRADIENTS['vivid']):
            tone=QColor(rgb);tone.setAlpha(26);wash.setColorAt(stop,tone)
        end=body_top if body_top is not None else rect.top()+min(38,rect.height()*.25)
        painter.fillRect(QRectF(rect.left(),rect.top(),rect.width(),max(0,end-rect.top())),wash)
    elif design=='aurora':
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
        if header_separator:
            stroke=QColor(accent);stroke.setAlpha(105);painter.setPen(QPen(stroke,1));painter.drawLine(QPointF(rect.left()+14,rect.top()+38),QPointF(rect.right()-14,rect.top()+38))
    else:
        color=blend(white,accent,.035);color.setAlpha(242);painter.fillPath(path,color)
    painter.restore()  # Stroke outside the fill clip, preserving antialiased edge coverage.
    edge=QLinearGradient(rect.topLeft(),rect.bottomRight());edge.setColorAt(0,blend(white,accent,.55));edge.setColorAt(.48,blend(white,accent,.18));edge.setColorAt(1,blend(white,accent,.65))
    painter.setBrush(Qt.NoBrush);painter.setPen(QPen(edge,1.4 if design=='aurora' else 1));painter.drawPath(path);painter.restore()
