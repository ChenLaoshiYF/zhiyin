# -*- coding: utf-8 -*-
"""纸音 · 品牌视觉：文案与 Logo 绘制

品牌名：纸音（Zhiyin），谐音「知音」——声音落纸成字，跨语言的心意相通。
Logo：深蓝渐变圆底 + 金色细环 + 一条米白声波线 + 金色纸页折角（声音落纸）。

launcher / subtitle_ui / main 共用本模块，保证品牌一致。
"""

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import QWidget

APP_NAME = "纸音"
APP_NAME_EN = "Zhiyin"
APP_SLOGAN = "老师的俄语，实时翻给你看"
APP_TITLE = "纸音 · 俄汉同传"

# 品牌色
INK_DEEP = QColor(43, 69, 87)      # 深蓝（圆底渐变暗端）
INK_MID = QColor(62, 96, 120)      # 中间蓝
INK_LIGHT = QColor(94, 135, 163)   # 浅蓝（圆底渐变亮端）
GOLD = QColor(190, 156, 88)        # 金色（环与纸角）
PAPER = QColor(246, 239, 223)      # 米白（声波）


def draw_logo(painter: QPainter, x: float, y: float, size: float,
              paper_color=QColor(246, 239, 223), gold_color=QColor(190, 156, 88)):
    """在 (x, y, size, size) 区域绘制「纸音」logo 内容（不含背景）。

    - 声波线：2 个周期正弦，从左下到右下，圆头笔
    - 纸角：声波末端上方一个金色小折角（声音落纸）
    """
    s = size
    # ---- 声波 ----
    wave = QPainterPath()
    n = 48
    wave.moveTo(QPointF(x + 0.17 * s, y + 0.54 * s))
    for i in range(1, n + 1):
        t = i / n
        px = x + 0.17 * s + t * 0.66 * s
        py = y + 0.54 * s - 0.115 * s * math.sin(t * 4 * math.pi)
        wave.lineTo(QPointF(px, py))
    pen = QPen(paper_color)
    pen.setWidthF(max(1.4, s * 0.075))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(wave)

    # ---- 纸角（声音落纸：声波末端上方的小折角） ----
    tri = QPainterPath()
    tri.moveTo(QPointF(x + 0.575 * s, y + 0.235 * s))
    tri.lineTo(QPointF(x + 0.755 * s, y + 0.235 * s))
    tri.lineTo(QPointF(x + 0.755 * s, y + 0.425 * s))
    tri.closeSubpath()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gold_color)
    painter.drawPath(tri)


class LogoWidget(QWidget):
    """圆形品牌徽标：金环 + 深蓝渐变圆 + 高光 + 纸音 logo。"""

    def __init__(self, size: int = 48, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        s = self.width()
        rect = QRectF(0, 0, s, s)

        # 外圈金环
        ring = QRectF(rect.adjusted(s * 0.015, s * 0.015, -s * 0.015, -s * 0.015))
        pen = QPen(QColor(GOLD.red(), GOLD.green(), GOLD.blue(), 150))
        pen.setWidthF(max(1.0, s * 0.032))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(ring)

        # 内圆深蓝渐变底
        inner = QRectF(rect.adjusted(s * 0.065, s * 0.065, -s * 0.065, -s * 0.065))
        grad = QLinearGradient(inner.topLeft(), inner.bottomRight())
        grad.setColorAt(0.0, QColor(INK_LIGHT))
        grad.setColorAt(0.55, QColor(INK_MID))
        grad.setColorAt(1.0, QColor(INK_DEEP))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grad)
        painter.drawEllipse(inner)

        # 左上高光（柔和，纸窗透光感）
        hi = QRadialGradient(QPointF(s * 0.38, s * 0.30), s * 0.55)
        hi.setColorAt(0.0, QColor(255, 255, 255, 46))
        hi.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(hi)
        painter.drawEllipse(inner)

        # logo 内容（声波 + 纸角）
        draw_logo(painter, inner.left(), inner.top(), inner.width())
        painter.end()
