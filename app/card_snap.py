"""Snap free desktop cards on release, using Qt logical screen coordinates."""
from PyQt5.QtCore import QRect
from PyQt5.QtWidgets import QApplication


def snap_target(rect, area, peers, distance):
    """Return the nearest valid adjacent edge and any screen edge it touches."""
    x, y, width, height = rect.getRect()
    edges = (
        (area.left() - x, 0, 'left'),
        (area.right() + 1 - x - width, 0, 'right'),
        (0, area.top() - y, 'top'),
        (0, area.bottom() + 1 - y - height, 'bottom'),
    )
    best = None

    def consider(dx, dy, edge):
        nonlocal best
        delta = abs(dx) + abs(dy)
        if delta > distance:
            return
        target = rect.translated(dx, dy)
        if not area.contains(target):
            return
        # A card already on one edge can still move along it to meet a peer.
        priority = (not delta, delta, edge == 'free')
        if best is None or priority < best[0]:
            best = priority, target, edge

    for dx, dy, edge in edges:
        consider(dx, dy, edge)
    for peer in peers:
        if not area.intersects(peer):
            continue
        if y <= peer.bottom() and rect.bottom() >= peer.top():
            consider(peer.left() - x - width, 0, 'free')
            consider(peer.right() + 1 - x, 0, 'free')
        if x <= peer.right() and rect.right() >= peer.left():
            consider(0, peer.top() - y - height, 'free')
            consider(0, peer.bottom() + 1 - y, 'free')
    return best[1:] if best else None


def resolve(window, runtime, point=None):
    cfg = runtime.dock.cfg
    if not cfg.get('card_snap', True):
        return None
    layout = getattr(runtime, 'layout', None)
    if layout and (layout.pending or layout.applying):
        return None
    rect = QRect(window.geometry())
    screen = (QApplication.screenAt(rect.center()) or
              (QApplication.screenAt(point) if point is not None else None) or
              QApplication.primaryScreen())
    if screen is None:
        return None
    cards = (*runtime.panels.windows.values(), *runtime.notes.windows.values(),
             runtime.clock, runtime.calendar, runtime.resources.window)
    peers = (card.geometry() for card in cards
             if card is not None and card is not window and card.isVisible() and not card.isMinimized())
    return snap_target(rect, screen.availableGeometry(), peers, cfg.get('card_snap_distance', 12))


def finish_drag(window, point):
    match = resolve(window, window.runtime, point)
    if match is not None:
        window.move(match[0].topLeft())
