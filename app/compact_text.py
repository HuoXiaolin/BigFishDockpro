"""Two-line text on the folded capsule's optical grid."""
from functools import lru_cache

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QColor, QFont, QFontMetricsF


def line_heights(height, style):
    gap = 1 if height < 26 else 2
    available = max(0, height-gap)
    upper = round(available * (.5 if style == 'rates' else .44))
    return upper, available-upper


@lru_cache(maxsize=64)
def readout_fonts(panel_height, dense):
    # Use the original widget type sizes. Only the clock sizes its glyphs to the tile.
    caption_size = 8 if panel_height < 38 else 9
    value_size = 10 if dense else 11
    if panel_height < 30:
        line_room = max(5, (panel_height-8)//2)
        caption_size = min(caption_size, line_room)
        value_size = min(value_size, line_room)
    caption = QFont()
    caption.setWeight(QFont.Normal)
    value = QFont(caption)
    caption.setPixelSize(caption_size)
    value.setPixelSize(value_size)
    return caption, value


def draw_stacked_text(painter, rect, rows, colors, style, fonts):
    if rect.isEmpty():
        return
    height = round(rect.height())
    heights = line_heights(height, style)
    painter.save()
    painter.setClipRect(rect, Qt.IntersectClip)
    for index, (value, color, font, room) in enumerate(zip(rows, colors, fonts, heights)):
        metrics = QFontMetricsF(font)
        advance = metrics.horizontalAdvance(value)
        if style != 'clock' and advance > rect.width():
            value = metrics.elidedText(value, Qt.ElideRight, rect.width())
        if not value or room <= 0:
            continue
        glyphs = metrics.tightBoundingRect(value)
        x = rect.left()
        scale = horizontal = 1.
        if style == 'clock':
            scale = min(1., room / (glyphs.height()+1))
            horizontal = min(scale, rect.width()/max(1.,advance))
            scale = min(scale,horizontal/.80)
            x = rect.center().x()-horizontal*advance/2
        # Anchor the ink, including Chinese fallback glyphs and descenders, at
        # the two outer edges. Font line spacing would leave unequal blank space.
        baseline = (rect.top()+.5-scale*glyphs.top() if index == 0 else
                    rect.bottom()-.5-scale*glyphs.bottom())
        painter.save()
        painter.setFont(font)
        painter.setPen(QColor(color))
        painter.translate(x, baseline)
        painter.scale(horizontal, scale)
        painter.drawText(QPointF(), value)
        painter.restore()
    painter.restore()
