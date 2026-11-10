"""Bundled provider marks for the compact AI display."""
from functools import lru_cache
from pathlib import Path
import sys

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QColor, QImage, QPainter, QPen


ICON_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'assets/ai-providers'
PROVIDER_MARKS = {
    'antigravity': 'antigravity.svg',
    'claude': 'claude-color.svg',
    'codex': 'codex.png',
    'commandcode': 'commandcode.svg', 'command code': 'commandcode.svg',
    'cursor': 'cursor.svg',
    'deepseek': 'deepseek-color.svg', 'dsh': 'deepseek-color.svg', 'deepseek harness': 'deepseek-color.svg',
    'grok': 'grok.svg', 'grokbot': 'grok.svg', 'grok bot': 'grok.svg',
    'kimi': 'kimi-color.svg', 'kimi code': 'kimi-color.svg',
    'opencode': 'opencode.svg', 'opencode go': 'opencode.svg',
    'openrouter': 'openrouter-color.svg',
    'pi': 'pi.svg',
    'zcode': 'zai.svg',
}


@lru_cache(maxsize=24)
def provider_art(mark, ink):
    path = ICON_DIR / mark
    if path.suffix == '.png':
        image = QImage(str(path))
        return None if image.isNull() else image

    from PyQt5.QtSvg import QSvgRenderer

    try:
        source = path.read_bytes()
    except OSError:
        return None
    renderer = QSvgRenderer(source.replace(b'currentColor', ink.encode('ascii')))
    return renderer if renderer.isValid() else None


def paint_provider_mark(painter, rect, provider, ink):
    color = QColor(ink)
    for field in ('brand', 'id', 'name'):
        mark = PROVIDER_MARKS.get(str(provider.get(field, '')).strip().casefold())
        if mark:
            art = provider_art(mark, color.name())
            if isinstance(art, QImage):
                painter.save()
                painter.setRenderHint(QPainter.SmoothPixmapTransform)
                painter.drawImage(rect, art)
                painter.restore()
                return
            if art:
                art.render(painter, rect)
                return

    # Unknown gateways share a small usage icon.
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(color, 1.25, Qt.SolidLine, Qt.RoundCap))
    painter.drawRoundedRect(rect.adjusted(1.5, 2.5, -1.5, -2.5), 2, 2)
    for index, height in enumerate((2, 4, 3)):
        x = rect.center().x() + (index - 1) * 2.7
        y = rect.center().y() + 2
        painter.drawLine(QPointF(x, y), QPointF(x, y - height))
