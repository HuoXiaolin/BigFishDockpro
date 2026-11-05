"""Contrast from the composed clock surface, with a bounded low-resolution map."""
from collections import OrderedDict
from PyQt5.QtCore import Qt,QRectF
from PyQt5.QtGui import QColor,QImage,QPainter

_surfaces=OrderedDict()

def luminance(color):
    def linear(v):return v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4
    return sum(w*linear(v) for w,v in zip((.2126,.7152,.0722),(color.redF(),color.greenF(),color.blueF())))

def contrast(left,right):
    a,b=sorted((luminance(left),luminance(right)));return (b+.05)/(a+.05)

def blend(left,right,amount):
    return QColor(*(round(a*(1-amount)+b*amount) for a,b in zip(left.getRgb()[:3],right.getRgb()[:3])))

def surface_map(key,width,height,backdrop,fallback,paint):
    """At most four 96x64 analysis images; no wallpaper or window is retained."""
    if key in _surfaces:
        _surfaces.move_to_end(key);return _surfaces[key]
    image=QImage(min(96,max(1,round(width))),min(64,max(1,round(height))),QImage.Format_RGB32)
    image.fill(fallback)
    p=QPainter(image);p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.scale(image.width()/max(1,width),image.height()/max(1,height))
    if backdrop is not None and not backdrop.isNull():
        p.drawPixmap(QRectF(0,0,width,height),backdrop,QRectF(0,0,backdrop.width(),backdrop.height()))
    paint(p);p.end();_surfaces[key]=image
    while len(_surfaces)>4:_surfaces.popitem(last=False)
    return image

def background_at(image,box,width,height):
    points=[]
    for y in (.22,.50,.78):
        for x in (.12,.31,.50,.69,.88):
            px=max(0,min(image.width()-1,round((box.x()+box.width()*x)/max(1,width)*(image.width()-1))))
            py=max(0,min(image.height()-1,round((box.y()+box.height()*y)/max(1,height)*(image.height()-1))))
            points.append(image.pixelColor(px,py))
    return points

def monochrome(backgrounds):
    """Pick solid white or black from the composed wallpaper/material surface."""
    if not backgrounds:return QColor('#000000')
    def score(ink):
        values=sorted(contrast(ink,bg) for bg in backgrounds)
        return values[len(values)//5]
    return max((QColor('#000000'),QColor('#ffffff')),key=score)


def colorful_ink(color,backgrounds,minimum=4.5):
    """Darken a saturated hue without blending it into grey; dark surfaces use white."""
    if monochrome(backgrounds).name()=='#ffffff':return QColor('#ffffff')
    color=QColor(color)
    if color.hsvSaturationF()<.4:color=QColor('#ce4125')
    for percent in (100,110,125,145,170,200,240,300):
        candidate=color.darker(percent)
        scores=sorted(contrast(candidate,bg) for bg in backgrounds)
        if not scores or scores[len(scores)//5]>=minimum:return candidate
    return color.darker(300)


def readable(color,backgrounds,minimum=4.5,opacity=1.0,polarity=None):
    """Preserve the chosen hue when readable; otherwise choose a clear ink tone."""
    color=QColor(color)
    levels=[luminance(bg) for bg in backgrounds]
    def score(candidate):
        if opacity>=.999:
            value=luminance(candidate)
            values=sorted((max(value,bg)+.05)/(min(value,bg)+.05) for bg in levels)
        else:values=sorted(contrast(blend(bg,candidate,opacity),bg) for bg in backgrounds)
        return values[max(0,len(values)//5)]
    if not backgrounds:return color
    same_polarity=polarity is None or (color.lightness()>150)==polarity
    if same_polarity and score(color)>=minimum:return color
    # Blue-black and soft white belong to the same family as the glass theme.
    goals=(QColor('#132b40'),QColor('#ffffff')) if polarity is None else (QColor('#ffffff' if polarity else '#132b40'),)
    goal=max(goals,key=score)
    # A short interpolation preserves custom accents without a grey mid-tone.
    for amount in (.35,.65,.85,1.0):
        candidate=blend(color,goal,amount)
        if (polarity is None or (candidate.lightness()>150)==polarity) and score(candidate)>=minimum:return candidate
    return goal

def clear_cache():_surfaces.clear()
