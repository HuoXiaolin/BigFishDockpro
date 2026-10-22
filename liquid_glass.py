"""The original Dock liquid-glass renderer, shared by desktop collection panels."""
from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import QColor, QLinearGradient, QRadialGradient, QBrush, QPen


def material_palette(colors, material):
    colors = dict(colors)
    strength = {'acrylic':.55, 'mica':.3, 'solid':0}.get(material, 1)
    colors['gloss'] = material == 'gloss'
    for key in ('grad','hl'):
        colors[key] = [(pos,round(alpha*strength)) for pos,alpha in colors[key]]
    colors['spec'] = round(colors['spec']*strength)
    return colors


def material_alpha(alpha, material):
    if material == 'clear': return min(alpha, 55)
    if material == 'mica': return max(alpha, 210)
    if material == 'solid': return 255
    return alpha


def tint_palette(palette, color):
    palette = dict(palette)
    accent = QColor(color)
    if not color or not accent.isValid(): return palette
    for key, ratio in [('tint', .38), ('border', .30)]:
        original = palette[key]
        palette[key] = QColor(round(original.red()*(1-ratio)+accent.red()*ratio),
                              round(original.green()*(1-ratio)+accent.green()*ratio),
                              round(original.blue()*(1-ratio)+accent.blue()*ratio), original.alpha())
    return palette


def paint_liquid_glass(surface, p, path, path_rect, bar, c, tint_a, stops):
    """画一段玻璃（隔断模式下会有好几段，每段都有自己的圆角）。

    整段只做一次 setClipPath —— 复杂路径的裁切光栅化是这里最贵的操作，
    之前每层各裁一次，一帧要裁好几遍，这就是鼠标滑动时占用偏高的主因。
    """
    if surface.cfg.get('clear_background', False): return
    tint_a = int(material_alpha(tint_a, surface.cfg.get('dock_material', 'liquid')))
    p.save()
    p.setClipPath(path)
    if surface.cfg["glass"] and surface.backdrop is not None:
        # 只画这一段所在的那块区域，避免整窗重绘浪费性能
        p.drawPixmap(path_rect, surface.backdrop, path_rect)
        if tint_a > 0:
            col = QColor(c["tint"])
            col.setAlpha(tint_a)
            p.fillRect(path_rect, col)
    else:
        col = QColor(c["tint"])
        col.setAlpha(min(255, tint_a + 20))
        p.fillRect(path_rect, col)

    # 竖向渐变 + 顶部高光（已经合并成一条渐变，省一次裁切+填充）
    # 注：实测这里用 QLinearGradient 直接填充比"缓存贴图再拉伸"更快，
    # 因为 Qt 的线性渐变填充走的是优化过的快路径。
    g = QLinearGradient(QPointF(0, path_rect.top()), QPointF(0, path_rect.bottom()))
    for pos, a in stops:
        g.setColorAt(pos, QColor(255, 255, 255, a))
    p.fillRect(path_rect, QBrush(g))

    # 跟着鼠标走的柔光（液态感的关键）
    # 只填"柔光实际照到的那一块"：半径外的颜色本来就是全透明，
    # 限制填充范围不改变画面，但能省掉几倍的像素量。
    if surface.spec_alpha > 0.01:
        wide = float(c.get("spec_wide", 1.2))
        radius = bar.height() * wide
        if path_rect.left() - radius <= surface.spec_x <= path_rect.right() + radius:
            rad = QRadialGradient(QPointF(surface.spec_x, bar.center().y()), radius)
            a = int(c["spec"] * surface.spec_alpha)
            rad.setColorAt(0.0, QColor(255, 255, 255, a))
            rad.setColorAt(0.55, QColor(255, 255, 255, int(a * 0.35)))
            rad.setColorAt(1.0, QColor(255, 255, 255, 0))
            box = QRectF(surface.spec_x - radius, path_rect.top(),
                         radius * 2.0, path_rect.height()).intersected(path_rect)
            if not box.isEmpty():
                p.fillRect(box, QBrush(rad))

    # 光感模式：再补一道斜向的"光扫过玻璃"的光带，就是那种带光照的观感
    # （同样只填光带实际覆盖的那一段，右边全透明的地方不浪费像素）
    if c.get("gloss"):
        gx0 = path_rect.left()
        gy0 = path_rect.top()
        sweep_w = path_rect.height() * 1.5
        sweep = QLinearGradient(QPointF(gx0, gy0),
                                QPointF(gx0 + sweep_w, path_rect.bottom()))
        sweep.setColorAt(0.00, QColor(255, 255, 255, 0))
        sweep.setColorAt(0.13, QColor(255, 255, 255, 132))
        sweep.setColorAt(0.30, QColor(255, 255, 255, 28))
        sweep.setColorAt(0.52, QColor(255, 255, 255, 0))
        sbox = QRectF(gx0, path_rect.top(), sweep_w,
                      path_rect.height()).intersected(path_rect)
        if not sbox.isEmpty():
            p.fillRect(sbox, QBrush(sweep))
    p.restore()

    # 描边（不需要裁切）
    pen = QPen(c["border"])
    pen.setWidthF(float(c.get("border_w", 1.0)))
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)

