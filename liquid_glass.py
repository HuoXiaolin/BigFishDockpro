"""The original Dock liquid-glass renderer, shared by desktop collection panels."""
from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import QColor, QLinearGradient, QRadialGradient, QBrush, QPen, QImage


def material_palette(colors, material):
    colors = dict(colors)
    strength = {'gloss':1.55, 'acrylic':.22, 'mica':.08, 'clear':.12, 'solid':0}.get(material, 1)
    colors['material'] = material
    if material=='mica':
        tint = QColor(colors['tint'])
        colors['tint'] = tint.darker(106) if colors.get('light',True) else tint.lighter(110)
    if material in ('acrylic','mica','clear'):
        border = QColor(colors['border'])
        border.setAlpha({'acrylic':55,'mica':30,'clear':45}[material])
        colors['border'] = border
    colors['gloss'] = material == 'gloss'
    for key in ('grad','hl'):
        colors[key] = [(pos,min(255,round(alpha*strength))) for pos,alpha in colors[key]]
    colors['spec'] = min(255,round(colors['spec']*({'mica':0,'acrylic':.12,'clear':.15}.get(material,strength))))
    return colors


def material_alpha(alpha, material):
    if material == 'clear': return min(alpha, 30)
    if material == 'acrylic': return max(alpha, 130)
    if material == 'mica': return max(alpha, 232)
    if material == 'solid': return 255
    return alpha


def material_blur(value, material):
    value = max(2,min(40,int(value)))
    if material=='acrylic': return max(16,min(40,value*2))
    if material=='mica': return max(24,min(40,value*3))
    if material=='gloss': return max(2,value//2)
    return value


from functools import lru_cache
@lru_cache(maxsize=2)
def grain_tile(material):
    tile = QImage(64,64,QImage.Format_ARGB32_Premultiplied)
    tile.fill(Qt.transparent)
    for y in range(64):
        for x in range(64):
            value = ((x+1)*73856093)^((y+1)*19349663)
            value ^= value>>13; value *= 1540483477; value ^= value>>15
            channel = 255 if value & 4 else 0
            tile.setPixelColor(x,y,QColor(channel,channel,channel,(value&3) if material=='acrylic' else (value&1)))
    return tile


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
        # QPainter's explicit source rectangle uses physical pixmap pixels,
        # even when the pixmap carries a DPR. The target remains logical.
        ratio=surface.backdrop.devicePixelRatio()
        source=QRectF(path_rect.x()*ratio,path_rect.y()*ratio,
                      path_rect.width()*ratio,path_rect.height()*ratio)
        p.drawPixmap(path_rect, surface.backdrop, source)
        if tint_a > 0:
            col = QColor(c["tint"])
            col.setAlpha(tint_a)
            p.fillRect(path_rect, col)
    else:
        col = QColor(c["tint"])
        col.setAlpha(min(255, tint_a + 20))
        p.fillRect(path_rect, col)

    material = surface.cfg.get('dock_material',c.get('material','liquid'))
    if material in ('acrylic','mica'): p.fillRect(path_rect,QBrush(grain_tile(material)))

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
        sweep_w = max(path_rect.height()*1.5,path_rect.width()*.85)
        sweep = QLinearGradient(QPointF(gx0, gy0),
                                QPointF(gx0 + sweep_w, path_rect.bottom()))
        sweep.setColorAt(0.00, QColor(255, 255, 255, 0))
        sweep.setColorAt(0.25, QColor(255, 255, 255, 12))
        sweep.setColorAt(0.38, QColor(255, 255, 255, 190))
        sweep.setColorAt(0.45, QColor(255, 255, 255, 28))
        sweep.setColorAt(0.60, QColor(255, 255, 255, 0))
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

