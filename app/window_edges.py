"""Pointer targets for resizing frameless desktop components."""
from PyQt5.QtCore import QRect, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QApplication


MARGIN = 9
LEFT, RIGHT, TOP, BOTTOM = map(int, (Qt.LeftEdge, Qt.RightEdge, Qt.TopEdge, Qt.BottomEdge))
CURSORS = {
    LEFT: Qt.SizeHorCursor,
    RIGHT: Qt.SizeHorCursor,
    TOP: Qt.SizeVerCursor,
    BOTTOM: Qt.SizeVerCursor,
    LEFT | TOP: Qt.SizeFDiagCursor,
    RIGHT | BOTTOM: Qt.SizeFDiagCursor,
    RIGHT | TOP: Qt.SizeBDiagCursor,
    LEFT | BOTTOM: Qt.SizeBDiagCursor,
}


def edges_at(rect, pos):
    if not rect.contains(pos):
        return 0
    horizontal = LEFT if pos.x() - rect.left() < MARGIN else RIGHT if rect.right() - pos.x() < MARGIN else 0
    vertical = TOP if pos.y() - rect.top() < MARGIN else BOTTOM if rect.bottom() - pos.y() < MARGIN else 0
    return horizontal | vertical


def resize_cursor(edges):
    return CURSORS.get(edges, Qt.SizeAllCursor)


def resized_rect(original, edges, delta, minimum):
    screen = QApplication.screenAt(original.center()) or QApplication.primaryScreen()
    if screen is None:
        return original
    area = screen.availableGeometry()
    min_width, min_height = min(minimum[0], area.width()), min(minimum[1], area.height())
    rect = QRect(original)
    if edges & LEFT:
        rect.setLeft(max(area.left(), min(original.left() + delta.x(), original.right() - min_width + 1)))
    elif edges & RIGHT:
        rect.setRight(min(area.right(), max(original.right() + delta.x(), original.left() + min_width - 1)))
    if edges & TOP:
        rect.setTop(max(area.top(), min(original.top() + delta.y(), original.bottom() - min_height + 1)))
    elif edges & BOTTOM:
        rect.setBottom(min(area.bottom(), max(original.bottom() + delta.y(), original.top() + min_height - 1)))
    return rect


def paint_edge_targets(painter, rect):
    # Windows skips fully transparent pixels during hit testing of a layered window.
    hit = QColor(0, 0, 0, 1)
    thickness = MARGIN - 1
    x, y, width, height = rect.adjusted(1, 1, -1, -1).getRect()
    if width <= 2 * thickness or height <= 2 * thickness:
        return
    painter.fillRect(QRect(x, y, width, thickness), hit)
    painter.fillRect(QRect(x, y + height - thickness, width, thickness), hit)
    painter.fillRect(QRect(x, y + thickness, thickness, height - 2 * thickness), hit)
    painter.fillRect(QRect(x + width - thickness, y + thickness, thickness, height - 2 * thickness), hit)
