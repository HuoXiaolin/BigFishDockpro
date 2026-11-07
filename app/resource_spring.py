# Adapted from Wisland (MIT), commit 35478b13897149b6927d932c06013bd5e21a2db3.
# Copyright (c) 2026 wisland contributors. See licenses/Wisland-MIT.txt.
# -*- coding: utf-8 -*-
"""弹簧动画：所有形变 / 位移都用阻尼弹簧，ratio < 1 时带弹性回弹。"""
from __future__ import annotations

import math


class Spring:
    __slots__ = ("x", "v", "target", "k", "c", "eps")

    def __init__(self, value: float = 0.0, stiffness: float = 300.0, ratio: float = 0.8, eps: float = 0.05):
        self.x = float(value)
        self.v = 0.0
        self.target = float(value)
        self.k = stiffness
        self.c = 2.0 * ratio * math.sqrt(stiffness)
        self.eps = eps

    def tune(self, stiffness: float, ratio: float):
        self.k = stiffness
        self.c = 2.0 * ratio * math.sqrt(stiffness)

    def to(self, target: float, stiffness: float | None = None, ratio: float | None = None):
        self.target = float(target)
        if stiffness is not None:
            self.tune(stiffness, ratio if ratio is not None else self.c / (2 * math.sqrt(self.k)))

    def snap(self, value: float):
        self.x = self.target = float(value)
        self.v = 0.0

    def step(self, dt: float):
        if self.rest:
            self.x = self.target
            self.v = 0.0
            return
        n = max(1, int(math.ceil(dt / (1 / 240))))
        h = dt / n
        for _ in range(n):
            a = -self.k * (self.x - self.target) - self.c * self.v
            self.v += a * h
            self.x += self.v * h

    @property
    def rest(self) -> bool:
        return abs(self.x - self.target) < self.eps and abs(self.v) < self.eps * 8


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def smooth(t: float) -> float:
    t = clamp(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def ease_out(t: float) -> float:
    t = clamp(t, 0.0, 1.0)
    return 1 - (1 - t) ** 3
