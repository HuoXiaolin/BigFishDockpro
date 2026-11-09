"""Snap free desktop cards on release, using Qt logical screen coordinates."""
from PyQt5.QtCore import QRect
from PyQt5.QtWidgets import QApplication


def edge_gaps(rect, area):
    return {'top': rect.top() - area.top(), 'bottom': area.bottom() - rect.bottom(),
            'left': rect.left() - area.left(), 'right': area.right() - rect.right()}


def touching_edge(rect, area, preferred='free', *, tolerance=0):
    gaps = edge_gaps(rect, area)
    if abs(gaps.get(preferred, tolerance + 1)) <= tolerance:
        return preferred
    edge = min(gaps, key=lambda key: abs(gaps[key]))
    return edge if abs(gaps[edge]) <= tolerance else 'free'


def snap_target(rect, area, peers, distance, *, snap_edges=True):
    """Return the nearest valid adjacent edge and any screen edge it touches."""
    x, y, width, height = rect.getRect()
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

    if snap_edges:
        gaps = edge_gaps(rect, area)
        consider(-gaps['left'], 0, 'left')
        consider(gaps['right'], 0, 'right')
        consider(0, -gaps['top'], 'top')
        consider(0, gaps['bottom'], 'bottom')
    for peer in peers:
        if not area.intersects(peer):
            continue
        if y <= peer.bottom() and rect.bottom() >= peer.top():
            consider(peer.left() - x - width, 0, 'free')
            consider(peer.right() + 1 - x, 0, 'free')
        if x <= peer.right() and rect.right() >= peer.left():
            consider(0, peer.top() - y - height, 'free')
            consider(0, peer.bottom() + 1 - y, 'free')
    if best is None:
        return None
    _, target, edge = best
    if snap_edges and edge == 'free':
        edge = touching_edge(target, area)
    return target, edge


def resolve(window, runtime, point=None, *, snap_edges=True, snap_peers=True):
    cfg = runtime.dock.cfg
    if not cfg.get('card_snap', True) or not (snap_edges or snap_peers):
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
    peers = ()
    if snap_peers:
        custom = getattr(runtime, 'custom_cards', None)
        cards = (*runtime.panels.windows.values(), *runtime.notes.windows.values(),
                 runtime.clock, runtime.calendar, runtime.resources.window, getattr(runtime, 'spectrum', None),
                 getattr(runtime, 'daily_picture', None),
                 *getattr(runtime.resources, 'desktop_cards', {}).values(),
                 *(custom.windows.values() if custom else ()))
        peers = (card.geometry() for card in cards
                 if card is not None and card is not window and card.isWindow() and card.isVisible() and not card.isMinimized())
    return snap_target(rect, screen.availableGeometry(), peers, cfg.get('card_snap_distance', 12), snap_edges=snap_edges)


def drop_rect(point, width, height):
    screen = QApplication.screenAt(point)
    if screen is None:
        return None
    area = screen.availableGeometry()
    width, height = min(width, area.width()), min(height, area.height())
    x = max(area.left(), min(point.x() - width // 2, area.right() + 1 - width))
    y = max(area.top(), min(point.y() - 14, area.bottom() + 1 - height))
    return [x, y, width, height]


def finish_drag(window, point, *, component=None, identity=None):
    if component and window.runtime.resources.return_component_at(component, point, identity):
        return True
    match = resolve(window, window.runtime, point)
    if match is not None:
        window.move(match[0].topLeft())
    return False
