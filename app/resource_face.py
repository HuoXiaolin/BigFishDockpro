# Adapted from Wisland (MIT), commit 35478b13897149b6927d932c06013bd5e21a2db3.
# Copyright (c) 2026 wisland contributors. See licenses/Wisland-MIT.txt.
import math,time
from PyQt5 import QtCore,QtGui
from PyQt5.QtCore import Qt
from resource_spring import clamp

class PetFace:
    """Wisland 小表情，适配本应用主题。

    常态：默认（东张西望）· 好奇（看向哪边那只眼变高）· 困倦（一分钟没人理）· 眨眼。
    鼠标靠近时随机换一种表情（不与上次重复）：
      开心 · 眨眼 · 爱心 · 星星眼 · 害羞 · 嘟嘴 · 眯眼
    s 为缩放（灵动岛上 1.0，主页上更大）。"""

    MOODS = ["happy", "wink", "love", "star", "shy", "pout", "squint"]

    def __init__(self):
        from resource_spring import Spring
        self.ex = Spring(0, 140, 0.8, 0.01)        # 视线
        self.ey = Spring(0, 140, 0.8, 0.01)
        self.lh = Spring(0, 160, 0.75, 0.003)      # 左眼下眼睑（开心月牙）
        self.rh = Spring(0, 160, 0.75, 0.003)      # 右眼下眼睑
        self.tired = Spring(0, 60, 1.0, 0.003)     # 上眼睑（困倦）
        self.wide = Spring(0, 220, 0.45, 0.003)    # 星星眼放大
        self.morph = Spring(0, 200, 0.7, 0.003)    # 特殊形状（爱心 / 眯眼 / 嘟嘴）出现的程度
        self.blush = Spring(0, 120, 0.9, 0.003)
        self.mood = "default"
        self.forced_mood = None
        self._last_mood = ""
        self._near = False
        self.blink_at = time.monotonic() + 2.5
        self.last_attention = time.monotonic()
        self._t = time.monotonic()
        self.spread = 0.0          # 被按压时两眼额外分开的距离（s=1 时的像素）
        self.tilt = 0.0            # 被按压时每只眼向外倾斜的角度

    def _pick(self):
        import random
        choices = [m for m in self.MOODS if m != self._last_mood]
        self.mood = random.choice(choices)
        self._last_mood = self.mood

    # ---------- 状态推进 ----------
    def _step(self, look: QtCore.QPointF, near: bool, s: float):
        now = time.monotonic()
        dt = min(0.05, max(0.001, now - self._t))
        self._t = now
        if self.forced_mood is not None:
            self.mood = self.forced_mood
        elif near and not self._near:
            self._pick()                       # 鼠标刚靠近：随机换表情
        self._near = near
        if near:
            self.last_attention = now
        m = self.forced_mood or self.mood
        self._m = m
        # 视线
        tx, ty = look.x() / (90.0 * s), look.y() / (60.0 * s)
        distance = max(1.,math.hypot(tx,ty))
        self.ex.to(tx/distance)
        self.ey.to(ty/distance)
        self.lh.to({"happy": 1, "laugh": 1, "shy": 0.55, "wink": 1}.get(m, 0) if m != "wink" else 0)
        self.rh.to({"happy": 1, "laugh": 1, "shy": 0.55, "wink": 1}.get(m, 0))
        self.tired.to(0.55 if (now - self.last_attention > 60 and m == "default") else 0.0)
        self.wide.to(0.3 if m == "star" else 0.0)
        self.morph.to(1.0 if m in ("love", "squint", "pout") else 0.0)
        self.blush.to({"shy": 1.0, "love": 0.8, "happy": 0.5, "laugh": 0.6, "wink": 0.5}.get(m, 0.0))
        for sp in (self.ex, self.ey, self.lh, self.rh, self.tired, self.wide, self.morph, self.blush):
            sp.step(dt)
        # 眨眼（特殊表情时不眨）
        dur = 0.16 + 0.18 * self.tired.x
        if now >= self.blink_at + dur:
            gap = 2.4 + (math.sin(now * 12.9898) * 0.5 + 0.5) * 3.2
            self.blink_at = now + gap * (1.6 if self.tired.x > 0.3 else 1.0)
        b = 0.0
        if self.blink_at <= now < self.blink_at + dur and m in ("default", "pout", "shy", "star"):
            b = math.sin((now - self.blink_at) / dur * math.pi)
        return b

    # ---------- 绘制 ----------
    @staticmethod
    def _heart(cx, cy, size) -> QtGui.QPainterPath:
        p = QtGui.QPainterPath()
        w = size
        p.moveTo(cx, cy + w * 0.42)
        p.cubicTo(cx - w * 0.9, cy - w * 0.05, cx - w * 0.45, cy - w * 0.75, cx, cy - w * 0.28)
        p.cubicTo(cx + w * 0.45, cy - w * 0.75, cx + w * 0.9, cy - w * 0.05, cx, cy + w * 0.42)
        p.closeSubpath()
        return p

    @staticmethod
    def _sparkle(cx, cy, r) -> QtGui.QPainterPath:
        p = QtGui.QPainterPath()
        p.moveTo(cx, cy - r)
        p.quadTo(cx, cy, cx + r, cy)
        p.quadTo(cx, cy, cx, cy + r)
        p.quadTo(cx, cy, cx - r, cy)
        p.quadTo(cx, cy, cx, cy - r)
        return p

    def paint(self, p: QtGui.QPainter, cx: float, cy: float, s: float, a: float,
              look: QtCore.QPointF, near: bool, colors, animate=True):
        def ink(alpha):
            color=QtGui.QColor(colors["ink"]);color.setAlphaF(alpha);return color
        if not animate:
            self._step(QtCore.QPointF(),False,s)
            for sp in (self.ex,self.ey,self.lh,self.rh,self.tired,self.wide,self.morph,self.blush):sp.x=sp.target;sp.v=0
        b = self._step(look, near, s) if animate else 0
        m = getattr(self, "_m", "default")
        now = time.monotonic()
        tired = clamp(self.tired.x, 0, 1)
        wide = clamp(self.wide.x, -0.3, 1.0)
        morph = clamp(self.morph.x, 0, 1)
        lx, ly = self.ex.x, self.ey.x
        bounce = math.sin(now * 16) * 1.6 * s if m == "laugh" else 0.0
        base_w, base_h, gap = 11.0 * s, 15.0 * s, 15.0 * s
        eye_col = ink(0.95 * a)
        glow_col = QtGui.QColor(colors["ink"]) if not colors["light"] else QtGui.QColor(0, 0, 0, 0)
        pink = QtGui.QColor(255, 92, 138)
        centers = []
        for side in (-1, 1):
            p.save()
            try:
                # 被按压时两只眼睛各自向外倾斜（按在中间时最明显）
                _ex0 = cx + side * (gap / 2 + base_w / 2 + self.spread * s / 2) + self.ex.x * 5.0 * s
                _ey0 = cy + self.ey.x * 3.0 * s
                if abs(self.tilt) > 0.05:
                    p.translate(_ex0, _ey0)
                    p.rotate(side * self.tilt)
                    p.translate(-_ex0, -_ey0)
                hap = clamp(self.lh.x if side < 0 else self.rh.x, 0, 1)
                curious = 1.0 + 0.22 * max(0.0, lx * side)
                w = base_w * (1 + 0.12 * wide) * (1 + 0.25 * b)
                h = base_h * curious * (1 + 0.18 * wide) * (1 - 0.88 * b)
                ex = cx + side * (gap / 2 + base_w / 2 + self.spread * s / 2) + lx * 5.0 * s
                ey = cy + ly * 3.0 * s + bounce
                centers.append((ex, ey))
                r = QtCore.QRectF(ex - w / 2, ey - h / 2, w, max(1.6 * s, h))
                # 光晕
                if glow_col.alpha() and a > 0.05:
                    g = QtGui.QRadialGradient(r.center(), max(r.width(), r.height()) * 0.85)
                    c1 = QtGui.QColor(pink if m == "love" else glow_col)
                    c1.setAlpha(round(85 * a))
                    c2 = QtGui.QColor(c1)
                    c2.setAlpha(0)
                    g.setColorAt(0.0, c1)
                    g.setColorAt(1.0, c2)
                    p.setPen(Qt.NoPen)
                    p.setBrush(g)
                    p.drawEllipse(r.center(), r.width() * 0.95, r.height() * 0.75 + 3 * s)
                # 特殊形状：爱心 / 眯眼 ><
                if m == "love" and morph > 0.05:
                    pulse = 1.0 + 0.08 * math.sin(now * 7)
                    p.setPen(Qt.NoPen)
                    hc = QtGui.QColor(pink)
                    hc.setAlphaF(a * morph)
                    p.setBrush(hc)
                    p.drawPath(self._heart(ex, ey, 15 * s * pulse * (0.6 + 0.4 * morph)))
                    continue
                if m == "squint" and morph > 0.05:
                    pen = QtGui.QPen(eye_col, 2.6 * s, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
                    p.setPen(pen)
                    p.setBrush(Qt.NoBrush)
                    d = -side                               # 左眼 ">"、右眼 "<"
                    k = 5.5 * s * morph
                    path = QtGui.QPainterPath()
                    path.moveTo(ex - d * k, ey - k)
                    path.lineTo(ex + d * k, ey)
                    path.lineTo(ex - d * k, ey + k)
                    p.drawPath(path)
                    continue
                rad = min(w, r.height()) * 0.42
                eye = QtGui.QPainterPath()
                eye.addRoundedRect(r, rad, rad)
                if tired > 0.01:
                    lid = QtGui.QPainterPath()
                    lid.addRect(QtCore.QRectF(r.left() - 2, r.top() - 2, r.width() + 4, 2 + r.height() * 0.5 * tired))
                    eye = eye.subtracted(lid)
                if m == "pout" and morph > 0.05:
                    # 嘟嘴：内侧上眼角斜切出"小眉头"
                    lid = QtGui.QPainterPath()
                    lid.addRect(QtCore.QRectF(-r.width(), -r.height(), r.width() * 2.2, r.height() * 1.0))
                    tr = QtGui.QTransform()
                    tr.translate(r.center().x() - side * r.width() * 0.1, r.top() + r.height() * 0.32 * morph)
                    tr.rotate(side * -24 * morph)
                    eye = eye.subtracted(tr.map(lid))
                if hap > 0.01:
                    cut_r = r.width() * 0.9
                    cc = QtCore.QPointF(r.center().x(), r.bottom() + cut_r - r.height() * 0.62 * hap)
                    lid = QtGui.QPainterPath()
                    lid.addEllipse(cc, cut_r, cut_r)
                    eye = eye.subtracted(lid)
                if not eye.isEmpty():
                    p.setPen(Qt.NoPen)
                    p.setBrush(eye_col)
                    p.drawPath(eye)
                if m == "star" and r.height() > 6 * s:
                    sc = QtGui.QColor(20, 20, 26, round(220 * a)) if colors["light"] else QtGui.QColor(30, 30, 40, round(200 * a))
                    p.setBrush(sc)
                    p.drawPath(self._sparkle(ex + 1.4 * s, ey - 2.2 * s, 3.4 * s))
                    p.drawPath(self._sparkle(ex - 2.2 * s, ey + 3.0 * s, 1.6 * s))

            finally:
                p.restore()
        # 腮红
        bl = clamp(self.blush.x, 0, 1)
        if bl > 0.02:
            for (ex, ey), side in zip(centers, (-1, 1)):
                c = QtGui.QColor(255, 124, 162, round(150 * bl * a))
                p.setPen(Qt.NoPen)
                p.setBrush(c)
                p.drawEllipse(QtCore.QPointF(ex + side * 7.5 * s, ey + base_h * 0.55), 4.4 * s, 2.4 * s)
        # 嘴
        mx = cx + lx * 5.0 * s
        my = cy + base_h * 0.66 + ly * 3.0 * s + bounce
        mc = ink(0.9 * a)
        p.setBrush(Qt.NoBrush)
        pen = QtGui.QPen(mc, 1.8 * s, Qt.SolidLine, Qt.RoundCap)
        if m in ("happy", "wink", "love", "shy"):
            path = QtGui.QPainterPath()
            mw = 7.0 * s
            path.moveTo(mx - mw / 2, my)
            path.quadTo(mx, my + 4.2 * s, mx + mw / 2, my)
            p.setPen(pen)
            p.drawPath(path)
        elif m == "laugh":
            path = QtGui.QPainterPath()
            mw = 9.0 * s
            path.moveTo(mx - mw / 2, my - 0.5 * s)
            path.quadTo(mx, my + 8.5 * s, mx + mw / 2, my - 0.5 * s)
            path.closeSubpath()
            p.setPen(Qt.NoPen)
            p.setBrush(mc)
            p.drawPath(path)
        elif m == "star":
            p.setPen(pen)
            p.drawEllipse(QtCore.QPointF(mx, my + 1.5 * s), 2.4 * s, 2.8 * s)
        elif m == "pout":
            p.setPen(pen)
            p.drawLine(QtCore.QPointF(mx - 3 * s, my + 1.5 * s), QtCore.QPointF(mx + 3 * s, my + 1.5 * s))
        elif m == "squint":
            path = QtGui.QPainterPath()
            mw = 6.0 * s
            path.moveTo(mx - mw / 2, my)
            path.quadTo(mx, my + 3.5 * s, mx + mw / 2, my)
            p.setPen(pen)
            p.drawPath(path)

