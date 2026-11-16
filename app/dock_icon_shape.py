"""Compose a circular background behind a Dock icon once when it is loaded."""
from math import sqrt

from PyQt5.QtCore import QRectF, QSize, Qt
from PyQt5.QtGui import QColor, QImage, QPainter, QPainterPath, QPixmap


def circular_icon(source, edge):
    if source.isNull():
        return source
    size = source.size().scaled(32, 32, Qt.KeepAspectRatio).expandedTo(QSize(1, 1))
    sample = source.toImage().scaled(size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    sample = sample.convertToFormat(QImage.Format_ARGB32)
    pixels = []
    red = green = blue = total = 0
    for y in range(sample.height()):
        for x in range(sample.width()):
            pixel = sample.pixel(x, y)
            alpha = pixel >> 24
            if alpha == 0:
                continue
            channels = ((pixel >> 16) & 255, (pixel >> 8) & 255, pixel & 255)
            weight = alpha * (64 + max(channels) - min(channels))
            red += channels[0] * weight
            green += channels[1] * weight
            blue += channels[2] * weight
            total += weight
            pixels.append((x, y))
    if not pixels:
        return source

    color = QColor(red // total, green // total, blue // total)
    hue, saturation, lightness, _ = color.getHsl()
    fill = QColor.fromHsl(hue, min(96, saturation), 116 if lightness >= 196 else 222)
    # Measure the visible silhouette. Fitting its outermost pixel preserves
    # square corners and gives rounded or narrow glyphs more room to breathe.
    xs, ys = zip(*pixels)
    cx = (min(xs) + max(xs) + 1) / 2
    cy = (min(ys) + max(ys) + 1) / 2
    dx = source.width() / sample.width()
    dy = source.height() / sample.height()
    radius = sqrt(max(((abs(x + .5 - cx) + .5) * dx) ** 2 +
                      ((abs(y + .5 - cy) + .5) * dy) ** 2 for x, y in pixels))
    scale = edge * .46 / radius
    target = QRectF(edge / 2 - cx * dx * scale, edge / 2 - cy * dy * scale,
                    source.width() * scale, source.height() * scale)

    result = QPixmap(edge, edge)
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    painter.setPen(Qt.NoPen)
    painter.setBrush(fill)
    outline = QPainterPath()
    outline.addEllipse(QRectF(0, 0, edge, edge))
    painter.drawPath(outline)
    painter.setClipPath(outline)
    painter.drawPixmap(target, source, QRectF(source.rect()))
    painter.end()
    return result
