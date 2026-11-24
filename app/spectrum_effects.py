"""Color spectrum effects driven by the desktop visualizer's audio frames."""
from functools import lru_cache
from math import cos, pi, sin, tau

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QBrush, QColor, QConicalGradient, QLinearGradient, QPainterPath, QPen, QPolygonF, QRadialGradient


SPECTRUM_COLORS = ('#4cdddf', '#639ffb', '#aa83fd', '#f38eba', '#ffd086')
CROWN_COLORS = ('#24c5c5', '#5580ef', '#905de8', '#df65bb', '#f2a064')
CROWN_PHASES_PER_COLUMN = 12
SPHERE_COLORS = ('#62eee9', '#71a5ff', '#bd8cff', '#ff91c1', '#ffda97', '#62eee9')


def _palette(gradient, colors):
    for index, color in enumerate(colors):
        gradient.setColorAt(index / (len(colors) - 1), QColor(color))
    return QBrush(gradient)


def _bands(values, count):
    if count >= len(values):
        return values
    edges = [i * len(values) // count for i in range(count + 1)]
    return [max(values[left:right]) for left, right in zip(edges, edges[1:])]


@lru_cache(maxsize=12)
def _directions(count):
    return tuple((cos(tau * i / count), sin(tau * i / count)) for i in range(count))


@lru_cache(maxsize=8)
def _crown_shades(count):
    colors = tuple(QColor(value).getRgbF() for value in CROWN_COLORS)
    shades = []
    for x, _ in _directions(count):
        position = (x + 1) / 2 * (len(colors) - 1)
        stop = min(int(position), len(colors) - 2)
        fraction = position - stop
        color = QColor.fromRgbF(*(a + (b - a) * fraction for a, b in zip(colors[stop], colors[stop + 1])))
        shades.append((color.darker(162), color.darker(112), color.lighter(143)))
    return tuple(shades)


@lru_cache(maxsize=CROWN_PHASES_PER_COLUMN)
def _crown_mesh(width, height, count, phase):
    radius_x, radius_y = width * .438, min(height * .136, width * .140)
    center = QPointF(width / 2, height * .722)
    half_step = min(.14, tau / count * .374)
    angle = tau * phase / (count * CROWN_PHASES_PER_COLUMN)
    turn_x, turn_y = cos(angle), sin(angle)
    directions = [(x * turn_x - y * turn_y, x * turn_y + y * turn_x) for x, y in _directions(count)]
    blocks = []
    for i in sorted(range(count), key=lambda index: directions[index][1]):
        x, y = directions[i]
        # Project the footprint of each rectangular block around the ring.
        def corner(radius, tangent):
            return center + QPointF(radius_x * (radius * x - tangent * y),
                                    radius_y * (radius * y + tangent * x))

        base = (corner(.925, -half_step), corner(1, -half_step),
                corner(1, half_step), corner(.925, half_step))
        faces = []
        for start in range(4):
            end = (start + 1) % 4
            if base[start].x() > base[end].x():
                faces.append((start, end))
        blocks.append((i, y, base, faces))
    return center, radius_x, radius_y, blocks


def draw_crown(painter, area, levels, _peaks, *, rotation=0.):
    width, height = area.width(), area.height()
    bands = list(_bands(levels, max(12, min(52, round(width / 6)))))
    pulse = bands + bands[::-1]
    count = len(pulse)
    # Reuse the projected positions within one column spacing. The levels and
    # colors move between those positions as the ring completes a turn.
    travel = round(rotation * count * CROWN_PHASES_PER_COLUMN / tau)
    shift, phase = divmod(travel, CROWN_PHASES_PER_COLUMN)
    center, radius_x, radius_y, blocks = _crown_mesh(width, height, count, phase)
    shades = _crown_shades(count)
    power = max(levels)
    painter.save()
    painter.translate(area.topLeft())

    light = QRadialGradient(0, .15, 1)
    light.setColorAt(0, QColor(105, 109, 236, 110))
    light.setColorAt(.60, QColor(99, 159, 244, 72))
    light.setColorAt(1, QColor(104, 186, 252, 0))
    painter.save()
    painter.translate(center.x(), center.y() - height * .15)
    painter.scale(radius_x, radius_y + height * .18)
    painter.setOpacity(.39 + .29 * power)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(light))
    painter.drawEllipse(QRectF(-1, -1, 2, 2))
    painter.restore()

    floor = QRectF(center.x() - radius_x * .88, center.y() - radius_y * .88,
                   radius_x * 1.76, radius_y * 1.76)
    floor_brush = _palette(QLinearGradient(floor.topLeft(), floor.bottomRight()),
                           ('#266b9e', '#5743a6', '#b269ae'))
    painter.setBrush(floor_brush)
    painter.setPen(QPen(QColor('#b1cbff'), 1))
    painter.setOpacity(.14 + .14 * power)
    painter.drawEllipse(floor)

    painter.setPen(Qt.NoPen)
    for i, depth, base, faces in blocks:
        band = (i - shift) % count
        rise = QPointF(0, height * (.0615 + .365 * pulse[band]))
        cap = tuple(point - rise for point in base)
        painter.setOpacity(.49 + .15 * depth)
        for first, last in faces:
            painter.setBrush(shades[band][first % 2])
            painter.drawConvexPolygon(QPolygonF((base[first], base[last], cap[last], cap[first])))
        painter.setOpacity(.81 + .12 * depth)
        painter.setBrush(shades[band][2])
        painter.drawConvexPolygon(QPolygonF(cap))
    painter.restore()


def draw_peak_bars(painter, area, levels, peaks):
    count = max(3, int(area.width() / 2.7))
    levels, peaks = _bands(levels, count), _bands(peaks, count)
    step = area.width() / len(levels)
    bottom = area.bottom() - 2
    travel = area.height() * .85
    width = max(.8, min(4, step * .56))
    base = QPainterPath()
    caps = QPainterPath()
    cap_glow = QPainterPath()
    cap_glow.setFillRule(Qt.WindingFill)
    cap_width = step * .91
    cap_height = min(1.3, cap_width * .24)
    for index, (level, peak) in enumerate(zip(levels, peaks)):
        x = area.left() + (index + .5) * step
        length = 1 + level * travel
        top = bottom - length
        base.addRect(QRectF(x - width / 2, top, width, length))
        if peak > .025:
            cap = QRectF(x - cap_width / 2, bottom - 3 - cap_height - peak * travel, cap_width, cap_height)
            caps.addRect(cap)
            cap_glow.addRect(cap.adjusted(-.35, -.45, .35, .45))
    brush = _palette(QLinearGradient(area.left(), 0, area.right(), 0), SPECTRUM_COLORS)
    painter.setOpacity(.96)
    painter.fillPath(base, brush)
    painter.setOpacity(.19)
    painter.fillPath(cap_glow, brush)
    painter.setOpacity(1)
    painter.fillPath(caps, brush)


@lru_cache(maxsize=2)
def _sphere_mesh(dense):
    rows, columns = (19, 38) if dense else (11, 22)
    points = []
    for row in range(rows + 1):
        latitude = pi * (row / rows - .5)
        ring = cos(latitude)
        y = sin(latitude)
        count = max(1, round(columns * ring))
        for column in range(count):
            angle = tau * (column + .5 * (row % 2)) / count
            points.append((ring * cos(angle), y, ring * sin(angle)))
    return tuple(points)


def sphere_power(levels):
    low_bands = levels[:max(1, len(levels) // 4)]
    energy = .63 * max(levels) + .37 * sum(low_bands) / len(low_bands)
    return min(1, max(0, (energy - .025) / .79))


def draw_particle_sphere(painter, area, levels, _peaks, *, rotation=0., power=None):
    center = area.center()
    radius = min(area.width(), area.height()) / 2
    power = sphere_power(levels) if power is None else power
    globe = radius * (.51 + .31 * power)
    spin_cos, spin_sin = cos(rotation), sin(rotation)
    tilt_cos, tilt_sin = cos(.27), sin(.27)
    mesh = ([], [], [])
    for x, y, z in _sphere_mesh(radius >= 77):
        rotated_x = x * spin_cos + z * spin_sin
        rotated_z = z * spin_cos - x * spin_sin
        vertical = y * tilt_cos - rotated_z * tilt_sin
        depth = y * tilt_sin + rotated_z * tilt_cos
        point = QPointF(center.x() + rotated_x * globe, center.y() + vertical * globe)
        mesh[0 if depth < 0 else 1 if depth < .55 else 2].append(point)
    brush = _palette(QLinearGradient(center.x() - radius, 0, center.x() + radius, 0), SPHERE_COLORS[:-1])
    dot = max(1, min(2.35, radius * .017))
    for i, points in enumerate(mesh):
        painter.setOpacity((.23 + i * .28) * (.58 + .42 * min(1, power * 2)))
        painter.setPen(QPen(brush, dot * (.78 + i * .24), Qt.SolidLine, Qt.RoundCap))
        painter.drawPoints(QPolygonF(points))

    # Keep the rim still so the movement reads as the mesh breathing inside it.
    painter.setBrush(Qt.NoBrush)
    rim = _palette(QConicalGradient(center, 95), SPHERE_COLORS)
    reach = radius * .90
    for width, opacity in ((.17, .10), (.10, .18), (.043, .92)):
        painter.setOpacity(opacity)
        painter.setPen(QPen(rim, max(1, radius * width)))
        painter.drawEllipse(center, reach, reach)


COLOR_EFFECTS = {
    'crown': draw_crown,
    'peak_bars': draw_peak_bars,
    'particle_sphere': draw_particle_sphere,
}
