# Adapted from Wisland (MIT), commit 35478b13897149b6927d932c06013bd5e21a2db3.
# Copyright (c) 2026 wisland contributors. See licenses/Wisland-MIT.txt.
# -*- coding: utf-8 -*-
"""液态形状几何。

坐标约定：所有函数都在屏幕(窗口)坐标下返回 QPainterPath。
"沿边坐标" (u, v)：u 沿着吸附边，v 垂直离开吸附边（v=0 就是屏幕边缘）。
  top:    x = u,         y = line + v
  bottom: x = u,         y = line - v
  left:   x = line + v,  y = u
  right:  x = line - v,  y = u

形状 = 胶囊本体（圆角矩形，贴边一侧的两个角半径随拉开距离从 0 长回去）
     ∪ 颈部（从屏幕边缘到本体的液桥，两侧是内凹曲线 —— 表面张力的圆角）
     ∪ 断开后残留在边缘、正在缩回的小水滴。
"""
from __future__ import annotations

import math

from PyQt5 import QtCore, QtGui

from resource_spring import clamp, lerp, smooth

K = 0.5523  # 四分之一圆弧的三次贝塞尔近似系数

QPointF = QtCore.QPointF


def edge_map(edge: str, line: float):
    if edge == "top":
        return lambda u, v: QPointF(u, line + v)
    if edge == "bottom":
        return lambda u, v: QPointF(u, line - v)
    if edge == "left":
        return lambda u, v: QPointF(line + v, u)
    return lambda u, v: QPointF(line - v, u)


def edge_is_horizontal(edge: str) -> bool:
    return edge in ("top", "bottom")


def edge_corners(edge: str | None) -> tuple[bool, bool, bool, bool]:
    """返回 (tl, tr, br, bl) 哪些角贴着吸附边。"""
    return {
        "top": (True, True, False, False),
        "bottom": (False, False, True, True),
        "left": (True, False, False, True),
        "right": (False, True, True, False),
    }.get(edge or "", (False, False, False, False))


def body_path(rect: QtCore.QRectF, radii: tuple[float, float, float, float]) -> QtGui.QPainterPath:
    """每个角独立半径的圆角矩形，顺时针：tl, tr, br, bl。"""
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    m = min(w, h) / 2
    tl, tr, br, bl = (clamp(r, 0, m) for r in radii)
    p = QtGui.QPainterPath()
    p.moveTo(x + tl, y)
    p.lineTo(x + w - tr, y)
    if tr:
        p.cubicTo(x + w - tr + tr * K, y, x + w, y + tr - tr * K, x + w, y + tr)
    p.lineTo(x + w, y + h - br)
    if br:
        p.cubicTo(x + w, y + h - br + br * K, x + w - br + br * K, y + h, x + w - br, y + h)
    p.lineTo(x + bl, y + h)
    if bl:
        p.cubicTo(x + bl - bl * K, y + h, x, y + h - bl + bl * K, x, y + h - bl)
    p.lineTo(x, y + tl)
    if tl:
        p.cubicTo(x, y + tl - tl * K, x + tl - tl * K, y, x + tl, y)
    p.closeSubpath()
    return p


def body_points(rect: QtCore.QRectF, radii, step: float = 5.0) -> list[tuple[float, float]]:
    """把圆角矩形均匀采样成多边形顶点（用于形变）。"""
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    m = min(w, h) / 2
    tl, tr, br, bl = (clamp(r, 0, m) for r in radii)
    pts: list[tuple[float, float]] = []

    def line(x0, y0, x1, y1):
        n = max(1, int(math.hypot(x1 - x0, y1 - y0) / step))
        for i in range(n):
            t = i / n
            pts.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))

    def arc(cx, cy, r, a0):
        if r <= 0.01:
            pts.append((cx, cy))
            return
        n = max(2, int(r * math.pi / 2 / step))
        for i in range(n):
            a = a0 + (math.pi / 2) * i / n
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))

    line(x + tl, y, x + w - tr, y)
    arc(x + w - tr, y + tr, tr, -math.pi / 2)
    line(x + w, y + tr, x + w, y + h - br)
    arc(x + w - br, y + h - br, br, 0)
    line(x + w - br, y + h, x + bl, y + h)
    arc(x + bl, y + h - bl, bl, math.pi / 2)
    line(x, y + h - bl, x, y + tl)
    arc(x + tl, y + tl, tl, math.pi)
    return pts


def deform(pts, cx: float, cy: float, vx: float, vy: float, half_extent: float,
           wave=None) -> list[tuple[float, float]]:
    """速度形变：后缘拖尾并收窄（泪滴），前缘略微鼓起；wave(x, y) 返回额外的法向位移。"""
    speed = math.hypot(vx, vy)
    amt = clamp(speed / 2600.0, 0.0, 1.0)
    if amt < 0.004 and wave is None:
        return pts
    if speed > 1e-3:
        dx, dy = vx / speed, vy / speed
    else:
        dx, dy = 0.0, 0.0
    lag = half_extent * 0.6 * amt
    out = []
    for (px, py) in pts:
        rx, ry = px - cx, py - cy
        d = math.hypot(rx, ry) or 1.0
        nx, ny = rx / d, ry / d
        if amt >= 0.004:
            s = nx * dx + ny * dy                 # 1 = 前缘, -1 = 后缘
            tf = (1.0 - s) * 0.5
            along = rx * dx + ry * dy
            perp_x, perp_y = rx - along * dx, ry - along * dy
            squeeze = 1.0 - 0.38 * amt * tf ** 1.2
            push = -lag * tf ** 1.6 + lag * 0.12 * (1 - tf) ** 2
            px = cx + along * dx + perp_x * squeeze + dx * push
            py = cy + along * dy + perp_y * squeeze + dy * push
        if wave is not None:
            w = wave(px, py, nx, ny)
            px += nx * w
            py += ny * w
        out.append((px, py))
    return out


def poly_path(pts) -> QtGui.QPainterPath:
    """多边形顶点 -> 平滑闭合路径（Catmull-Rom 转贝塞尔）。"""
    p = QtGui.QPainterPath()
    n = len(pts)
    if n < 3:
        return p
    p.moveTo(*pts[0])
    for i in range(n):
        p0 = pts[i - 1]
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        p3 = pts[(i + 2) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        p.cubicTo(c1[0], c1[1], c2[0], c2[1], p2[0], p2[1])
    p.closeSubpath()
    return p


def neck_path(edge: str, line: float, c: float, length: float, gap: float, t: float,
              strength: float, fillet: float, corner: float) -> QtGui.QPainterPath:
    """边缘 -> 本体的液桥。

    c: 本体沿边中心；length: 本体沿边长度；gap: 本体到边缘的距离；
    t: 拉伸程度 0(完全贴合)..1(即将断开)；strength: 0..1 颈部形成/消失的过渡；
    fillet: 贴合时两侧内凹圆角半径；corner: 本体贴边一侧角的当前圆角半径。
    """
    if strength <= 0.01:
        return QtGui.QPainterPath()
    m = edge_map(edge, line)
    half = length / 2
    tc = clamp(t, 0.0, 1.0)
    ts = math.sqrt(tc)
    # 沙漏形液桥：边缘侧内凹圆角 -> 中间收腰 -> 本体侧内凹圆角
    wz = lerp(half, max(2.5, min(7.0, length * 0.035)), ts)        # 腰部半宽
    wz = lerp(1.0, wz, strength)
    fe = lerp(fillet, fillet * 0.75, tc) * strength                 # 边缘侧圆角
    fb = fillet * smooth(tc * 3.0) * strength                       # 本体侧圆角（拉开后才出现）
    e = wz + fe
    b = min(wz + fb, max(wz, half - corner * 0.5))
    # 没入本体的深度（被并集吃掉）。贴合时要够深，盖住本体多边形被平滑掉的贴边直角，避免两侧露缝
    ov = max(min(8.0, corner + 3.0), fillet * (1.0 - tc))
    ym = max(gap * 0.5, fe)                                         # 腰部位置
    yb = gap + 0.5                                                  # 本体顶面

    def side(sg):
        """返回一侧的曲线段（sg=+1 右侧，-1 左侧），从边缘走向本体。"""
        segs = [(m(c + sg * (wz + (e - wz) * (1 - K)), 0), m(c + sg * wz, ym * (1 - K)), m(c + sg * wz, ym))]
        if yb > ym + 0.5:
            segs.append((m(c + sg * wz, ym + (yb - ym) * K), m(c + sg * (b - (b - wz) * K), yb), m(c + sg * b, yb)))
            end = m(c + sg * b, gap + ov)
        else:
            end = m(c + sg * wz, gap + ov)
        return segs, end

    rs, rend = side(1)
    ls, lend = side(-1)
    path = QtGui.QPainterPath()
    path.moveTo(m(c - e, -1.5))
    path.lineTo(m(c + e, -1.5))
    path.lineTo(m(c + e, 0))
    for c1, c2, p3 in rs:
        path.cubicTo(c1, c2, p3)
    path.lineTo(rend)
    path.lineTo(lend)
    # 左侧反向走回边缘
    pts = [m(c - e, 0)] + [seg[2] for seg in ls]
    rev = []
    for i in range(len(ls) - 1, -1, -1):
        c1, c2, _ = ls[i]
        rev.append((c2, c1, pts[i]))
    path.lineTo(ls[-1][2])
    for c1, c2, p3 in rev:
        path.cubicTo(c1, c2, p3)
    path.closeSubpath()
    return path


def drip_path(edge: str, line: float, c: float, r: float) -> QtGui.QPainterPath:
    """断开后留在边缘、正在缩回的半个小水滴（同样带表面张力圆角）。"""
    path = QtGui.QPainterPath()
    if r <= 0.4:
        return path
    m = edge_map(edge, line)
    f = r * 0.8
    path.moveTo(m(c - r - f, -1.5))
    path.lineTo(m(c + r + f, -1.5))
    path.lineTo(m(c + r + f, 0))
    path.cubicTo(m(c + r + f * (1 - K), 0), m(c + r, f * (1 - K)), m(c + r, f * 0.9))
    path.cubicTo(m(c + r, f + r * 0.9), m(c - r, f + r * 0.9), m(c - r, f * 0.9))
    path.cubicTo(m(c - r, f * (1 - K)), m(c - r - f * (1 - K), 0), m(c - r - f, 0))
    path.closeSubpath()
    return path
