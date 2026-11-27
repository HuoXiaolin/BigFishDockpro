"""Hand-painted almanac face shared by the calendar and the reverse of the clock."""
from datetime import datetime
from functools import lru_cache
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QColor, QFont, QFontMetricsF, QImageReader, QLinearGradient, QPainter, QPainterPath, QPixmap
from calendar_almanac import almanac, ASSETS, ROTATION_MINUTES, edition, next_civil_holiday, next_festival, verse_index


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


def calendar_controls(width):
    return (18, 30, 18, 20) if width < 238 else (23, 38, 23, 23)


def almanac_padding(width, height):
    return max(7, min(22, width * .055, height * .062))


def _paper_wash(painter, box, gradient, paper, stops):
    for stop, alpha in stops:
        tint = QColor(paper)
        tint.setAlpha(alpha)
        gradient.setColorAt(stop, tint)
    painter.fillRect(box, gradient)


def _painting(painter, body, picture, paper, light, header_bottom, verse_y):
    w, h = body.width(), body.height()
    painter.fillRect(body, paper)
    if picture.isNull():
        return
    sx, sy = w / picture.width(), h / picture.height()
    # Keep the right-hand subject in frame when a portrait card crops the paper.
    scale = min(max(sx, sy), 1.7 * sx, 1.35 * sy)
    pw, ph = picture.width() * scale, picture.height() * scale
    scene = QRectF(w - pw, (h - ph) * .48, pw, ph)
    painter.setOpacity(1 if light else .77)
    painter.drawPixmap(scene, picture, QRectF(picture.rect()))
    painter.setOpacity(1)
    if ph < h - 2:
        _paper_wash(painter, scene, QLinearGradient(0, scene.top(), 0, scene.bottom()), paper,
                    ((0, 255), (.14, 0), (.86, 0), (1, 255)))
    _paper_wash(painter, body, QLinearGradient(0, 0, w, 0), paper,
                ((0, 242), (.32, 205), (.61, 55 if light else 104), (1, 0 if light else 23)))
    _paper_wash(painter, QRectF(0, 0, w, header_bottom), QLinearGradient(0, 0, 0, header_bottom), paper,
                ((0, 182 if light else 213), (.58, 124 if light else 168), (1, 0)))
    footer_top = verse_y - 9
    _paper_wash(painter, QRectF(0, footer_top, w, h-footer_top),
                QLinearGradient(0, footer_top, 0, h), paper,
                ((0, 0), (.42, 169 if light else 202), (1, 232)))


def draw_almanac(painter, rect, dock, options):
    now = options.get('_now') or datetime.now()
    day = options.get('_almanac_date') or now.date()
    model = almanac(day)
    if model is None:
        painter.fillRect(rect, QColor('#f6eedf'))
        _line(painter, rect.adjusted(10,0,-10,0), '农历节气支持 1901–2099 年', options['date_font'], 14, QColor('#40392c'))
        return '#40392c'
    art = model.card(options.get('_almanac_art', 0))
    version = edition(now)
    events = model.events
    light = (options.get('_host_palette') or dock.base_theme_colors(options['theme']))['light']
    mode=options.get('content_mode','auto')
    if mode!='auto':light=dock.base_theme_colors(dock.cfg.get('theme','auto'))['light'] if mode=='app' else mode=='light'
    ink = QColor('#252f29' if light else '#fff7e5')
    detail = QColor('#52594e' if light else '#e2decc')
    accent = QColor(('#874129' if model.festival or model.civil_festival else '#385d50') if light else '#f5d89e')
    from desktop_clock import contrast_ink
    paper = QColor('#f6efdf' if light else '#263532')
    if mode=='auto' and not options['auto_contrast'] and options['text_color']:
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
        pad = almanac_padding(w, h)
        usable = w - 2*pad
        tight = h < 142
        size_factor = options['date_scale']/100
        family = options['date_font']
        def line(box, value, size, color=ink, weight=QFont.Normal, face=family):
            _line(painter, box, value, face, size*size_factor, color, weight)

        controls = options.get('_almanac_controls','')
        reserve = sum(calendar_controls(w)) + 10 if controls=='calendar' else 22 if controls=='clock' else 0
        weekday = '周'+'一二三四五六日'[day.weekday()]
        stamp = f'{day.month}月{day.day}日  {weekday}' if usable-reserve>=90 else f'{day.month}/{day.day}  {weekday}'
        header = QRectF(pad, 5 if tight else 9, usable-reserve, 14 if tight else 24)
        main = art.name if events else model.lunar
        secondary = ' · '.join((model.lunar, *(name for name in events if name != art.name))) if events else f'{model.term}时节'
        lunar_name, lunar_days = next_festival(day)
        civil_name, civil_days = (model.civil_festival, 0) if model.civil_names else next_civil_holiday(day)
        upcoming = [(name, days) for name,days in ((model.next_term,model.days_left),
                    (lunar_name,lunar_days),(civil_name,civil_days)) if name]
        from calendar_markers import upcoming_countdowns
        personal=upcoming_countdowns(dock.cfg,day,now)

        verse_h = min(27, max(13, h*.12))
        verse_y = h-pad-verse_h
        _painting(painter, body, illustration(art.key, version), paper, light, header.bottom()+9, verse_y)
        line(header, stamp, 10 if tight else 13, detail)
        top = header.bottom() + min(9,h*.025)
        bottom = verse_y - min(13,h*.045)
        available = max(1,bottom-top)
        content_w = min(usable, max(132, usable*(.66 if w>=300 else .79)))
        if personal:
            # Keep a holiday and a personal date together even on the narrow face.
            # Additional dates share the existing almanac rotation and animation.
            content_w=min(usable,max(content_w,usable*.89))
            slots=max(2,min(6,int(content_w//54)))
            slot=(now.hour*60+now.minute)//ROTATION_MINUTES
            holiday_slots=min(len(upcoming),slots-1)
            if holiday_slots<len(upcoming):
                upcoming=[upcoming[(slot+i)%len(upcoming)] for i in range(holiday_slots)]
            places=min(len(personal),slots-holiday_slots)
            start=(slot*places)%len(personal) if places<len(personal) else 0
            upcoming.extend(personal[(start+i)%len(personal)] for i in range(places))
        title_h = available*.39
        subtitle_h = available*.16
        face = 'SimSun'
        line(QRectF(pad,top,content_w,title_h), main, min(44,title_h*.90), ink, QFont.DemiBold, face)
        line(QRectF(pad,top+title_h,content_w,subtitle_h), secondary,
             min(13,subtitle_h*.95), accent, QFont.Medium)

        # All names and values share baselines with the holiday reminders.
        grid_y = top+title_h+subtitle_h + available*.075
        cell_w = min(content_w/len(upcoming), 74) if upcoming else 0
        name_h = (bottom-grid_y)*.45
        for index,(name,days) in enumerate(upcoming):
            x = pad+index*cell_w
            if index:
                pen = QColor(detail);pen.setAlpha(57)
                painter.fillRect(QRectF(x-4,grid_y+2,.8,max(2,bottom-grid_y-4)),pen)
            name_size=min(13,name_h)
            if personal:
                font=QFont(family);font.setPixelSize(max(1,round(name_size*size_factor)))
                name=QFontMetricsF(font).elidedText(name,Qt.ElideRight,max(1,cell_w-6))
            line(QRectF(x,grid_y,cell_w-6,name_h),name,name_size,detail)
            box = QRectF(x,grid_y+name_h,cell_w-6,bottom-grid_y-name_h)
            line(box, f'{days}天' if days else '今天',min(18,box.height()),accent if index==0 else ink,QFont.DemiBold)
        quote_width = usable - options.get('_almanac_switch_width', 0)
        verse = QRectF(pad,verse_y,quote_width,verse_h)
        line(verse,art.verses[verse_index(now)],11 if tight else min(17,13+w/180),face=face)
    finally:
        painter.restore()
    return ink.name()
