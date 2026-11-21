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
    ink = QColor('#252f29' if light else '#fff7e5')
    detail = QColor('#52594e' if light else '#e2decc')
    accent = QColor(('#874129' if model.festival or model.civil_festival else '#385d50') if light else '#f5d89e')
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
        rows = [(secondary, 11 if tight else 13, detail, QFont.Normal),
                (f'距{model.next_term} {model.days_left} 天', 11 if tight else 16, accent, QFont.DemiBold)]
        if not tight:
            upcoming, distance = next_festival(day)
            if upcoming:
                rows.append((f'距{upcoming} {distance} 天', 13, detail, QFont.Normal))
        rows.append((model.civil_countdown(), 11 if tight else 13, detail, QFont.Normal))

        verse_h = 16 if tight else max(20, min(29, h * .105))
        verse_y = h - pad * .58 - verse_h
        content_top = header.bottom() + (2 if tight else 5)
        content_height = verse_y - content_top - (4 if tight else 10)
        title_h = min(60, h * .185)
        row_h = min(13 if tight else 24, (content_height-title_h)/len(rows))
        content_y = content_top + (content_height-title_h-len(rows)*row_h) * .35
        title_width = usable * (.82 if w < 250 else .67)
        rows_width = usable * (.80 if w < 250 else .58)
        _painting(painter, body, illustration(art.key, version), paper, light, header.bottom()+11, verse_y)

        line(header, stamp, 11 if tight else 13, detail)
        face = 'Microsoft YaHei UI' if version else 'SimSun'
        line(QRectF(pad, content_y, title_width, title_h), main, min(44, title_h*.88), ink, QFont.DemiBold, face)
        for index, (value, size, color, weight) in enumerate(rows):
            line(QRectF(pad, content_y+title_h+index*row_h, rows_width, row_h), value, size, color, weight)
        quote_width = usable - options.get('_almanac_switch_width', 0)
        verse = QRectF(pad, verse_y, quote_width, verse_h)
        line(verse, art.verses[verse_index(now)], 11 if tight else min(17, 13+w/180), face='SimSun')
    finally:
        painter.restore()
    return ink.name()
