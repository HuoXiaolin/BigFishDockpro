"""Hand-painted almanac face shared by the calendar and the reverse of the clock."""
from datetime import datetime
from functools import lru_cache
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QColor, QFont, QFontMetricsF, QImageReader, QLinearGradient, QPainter, QPainterPath, QPixmap
from calendar_almanac import almanac, ASSETS, edition, next_festival, verse_index


@lru_cache(maxsize=2)
def illustration(key, version):
    suffix = '-print' if version else ''
    # Loading a filename directly into QPixmap also retains it in Qt's global cache.
    reader = QImageReader(str(ASSETS / 'pictures' / f'{key}{suffix}.jpg'))
    return QPixmap.fromImage(reader.read())


def _line(painter, box, value, family, size, color, weight=QFont.Normal):
    if box.width() < 1 or box.height() < 1 or not value:
        return
    font = QFont(family)
    font.setWeight(weight)
    font.setPixelSize(max(1, round(size)))
    metrics = QFontMetricsF(font)
    factor = min(1, box.width()/max(1, metrics.horizontalAdvance(value)), box.height()/metrics.height())
    if factor < 1:
        font.setPixelSize(max(1, int(font.pixelSize()*factor)))
    painter.setFont(font)
    painter.setPen(color)
    painter.drawText(box, Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine, value)


def draw_almanac(painter, rect, dock, options):
    now = options.get('_now') or datetime.now()
    day = options.get('_almanac_date') or now.date()
    model = almanac(day)
    if model is None:
        painter.fillRect(rect, QColor('#f6eedf'))
        _line(painter, rect.adjusted(10,0,-10,0), '农历节气支持 1901–2099 年', options['date_font'], 14, QColor('#40392c'))
        return '#40392c'
    art = model.card(options.get('_almanac_prefer_term', False))
    version = edition(now)
    event = model.term_today or bool(model.festival)
    light = (options.get('_host_palette') or dock.base_theme_colors(options['theme']))['light']
    ink = QColor('#252f29' if light else '#fff7e5')
    detail = QColor('#52594e' if light else '#e2decc')
    accent = QColor(('#874129' if model.festival else '#385d50') if light else '#f5d89e')
    from desktop_clock import contrast_ink
    paper = QColor('#f6efdf' if light else '#263532')
    if not options['auto_contrast'] and options['text_color']:
        ink = contrast_ink(options['text_color'], paper, 4.5)
    if options['accent_color']:
        accent = contrast_ink(options['accent_color'], paper, 4.5)

    painter.save()
    try:
        painter.translate(rect.topLeft())
        w,h = rect.width(),rect.height()
        body = QRectF(0,0,w,h)
        shape = QPainterPath()
        radius = 0 if options.get('_host_palette') else min(options['corner_radius'], h/5)
        shape.addRoundedRect(body,radius,radius)
        painter.setRenderHints(QPainter.Antialiasing|QPainter.SmoothPixmapTransform|QPainter.TextAntialiasing)
        painter.setClipPath(shape,Qt.IntersectClip)
        painter.fillRect(body,paper)
        picture = illustration(art.key, version)
        if not picture.isNull():
            # Trim the blank left margin first. On extreme aspect ratios,
            # feather the edge into the paper to keep the subject in view.
            sx,sy = w/picture.width(),h/picture.height()
            scale = min(max(sx,sy),1.55*sx,1.35*sy)
            pw,ph = picture.width()*scale,picture.height()*scale
            image_box = QRectF(w-pw,(h-ph)*.48,pw,ph)
            painter.setOpacity(1 if light else .72)
            painter.drawPixmap(image_box,picture,QRectF(picture.rect()))
            painter.setOpacity(1)
            if ph<h-2:
                fade = QLinearGradient(0,image_box.top(),0,image_box.bottom())
                transparent=QColor(paper);transparent.setAlpha(0)
                for stop,tint in ((0,paper),(.13,transparent),(.87,transparent),(1,paper)):
                    fade.setColorAt(stop,tint)
                painter.fillRect(image_box,fade)
        wash = QLinearGradient(0,0,w,0)
        for stop,alpha in ((0,246),(.34,207),(.64,24 if light else 79),(1,0 if light else 25)):
            tint = QColor(paper); tint.setAlpha(alpha); wash.setColorAt(stop,tint)
        painter.fillRect(body,wash)
        pad = max(9,min(24,w*.055,h*.078))
        usable = w-2*pad
        tight = h < 145
        size_factor = options['date_scale']/100
        family = options['date_font']
        def line(y, height, value, size, color=ink, weight=QFont.Normal, width=usable, face=family):
            _line(painter,QRectF(pad,y,width,height),value,face,size*size_factor,color,weight)

        controls = options.get('_almanac_controls','')
        reserve = 116 if controls=='calendar' else 27 if controls=='clock' else 0
        stamp = f'{day.month}月{day.day}日  周{"一二三四五六日"[day.weekday()]}'
        line(5 if tight else 8,19 if tight else 26,stamp,11 if tight else 13,detail,width=max(35,usable-reserve))
        main = art.name if event else model.lunar
        alternate = model.term if art.name==model.festival else model.festival
        secondary = model.lunar if event else f'{model.term}时节'
        if event and alternate and model.festival and model.term_today:
            secondary += ' · '+alternate
        verse_size = min(18,max(10,w*.038))
        verse_h = max(19,min(44,h*.17))
        quote_y = h-verse_h
        # Keep the daily verse readable over detailed festival paintings.
        foot = QLinearGradient(0,quote_y-5,0,h)
        for stop,alpha in ((0,0),(.35,192),(1,241)):
            tint = QColor(paper); tint.setAlpha(alpha); foot.setColorAt(stop,tint)
        painter.fillRect(QRectF(0,quote_y-5,w,verse_h+5),foot)
        title_y = 24 if tight else max(40,h*.24)
        title_h = min(h*.21,64) if not tight else max(18,h*.19)
        line(title_y,title_h,main,min(45,max(16,w*.093)),ink,QFont.DemiBold,
             width=usable*.78,face='Microsoft YaHei UI' if version else 'SimSun')
        label_y = title_y+title_h
        if not tight:
            line(label_y, min(25,h*.105),secondary,14,detail,width=usable*.80)
        countdown = f'距{model.next_term} {model.days_left} 天'
        if tight:
            line(label_y, max(13,(quote_y-label_y)/2),secondary,11,detail)
            line((label_y+quote_y)/2, max(13,(quote_y-label_y)/2),countdown,12,accent,QFont.DemiBold)
        else:
            count_y = max(label_y+min(25,h*.105)+3,quote_y-59)
            line(count_y,25,countdown,16,accent,QFont.DemiBold)
            upcoming, distance = next_festival(day)
            if upcoming and count_y+41<=quote_y:
                line(count_y+23,19,f'距{upcoming} {distance} 天',12,detail)
        line(quote_y,verse_h,art.verses[verse_index(now)],verse_size,ink,width=usable,face='SimSun')
    finally:
        painter.restore()
    return ink.name()
