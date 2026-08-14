# -*- coding: utf-8 -*-
"""矢量图标按钮：QPainter 手绘极简图标 + 保留文字标签

用 QPainter 画抗锯齿矢量图标（暂停/播放/穿透/交互/退出/翻看/复位），
按钮文字保持原有文本（"暂停"/"继续"/"穿透"/"交互"/"退出"/"翻看"/"恢复"/"复位"），
既有精致图标，又不破坏依赖 text() 的业务逻辑与测试。

图标画在按钮左侧，文字需在 QSS 里留出左侧内边距（padding-left 约 26px）。
"""

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QPushButton

_ICON_W = 14      # 图标区域宽度
_ICON_X = 12      # 图标左侧起始


def _ink(button) -> QColor:
    """取按钮当前文字颜色（QSS 设置的 color 会同步进 palette）。"""
    c = button.palette().color(button.foregroundRole())
    return c if c.isValid() else QColor(90, 86, 78)


def _path_icon(button, painter, kind):
    """在按钮左侧画出 kind 对应的图标。kind: pause/play/lock/unlock/exit/view/reset"""
    x = _ICON_X
    y0 = button.height() / 2.0
    ink = _ink(button)
    pen = QPen(ink)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    if kind in ("pause", "play"):
        # 暂停：两条圆角竖条；播放：右三角（填充）
        pen.setWidthF(3.0)
        painter.setPen(pen)
        if kind == "pause":
            for dx in (-3.5, 3.5):
                painter.drawLine(QPointF(x + dx, y0 - 6), QPointF(x + dx, y0 + 6))
        else:
            painter.setBrush(ink)
            painter.setPen(Qt.PenStyle.NoPen)
            path = QPainterPath()
            path.moveTo(x - 4.5, y0 - 6.5)
            path.lineTo(x + 5.5, y0)
            path.lineTo(x - 4.5, y0 + 6.5)
            path.closeSubpath()
            painter.drawPath(path)
    elif kind in ("lock", "unlock"):
        # 穿透：空心圆环（鼠标可穿过）；交互：实心圆
        if kind == "lock":
            pen.setWidthF(2.2)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(x - 5.5, y0 - 5.5, 11, 11))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(ink)
            painter.drawEllipse(QRectF(x - 4.5, y0 - 4.5, 9, 9))
    elif kind == "exit":
        # 关闭：细十字叉
        pen.setWidthF(2.4)
        painter.setPen(pen)
        painter.drawLine(QPointF(x - 5, y0 - 5), QPointF(x + 5, y0 + 5))
        painter.drawLine(QPointF(x + 5, y0 - 5), QPointF(x - 5, y0 + 5))
    elif kind == "view":
        # 翻看：上下箭头
        pen.setWidthF(2.2)
        painter.setPen(pen)
        painter.drawLine(QPointF(x, y0 - 6.5), QPointF(x, y0 + 6.5))
        painter.drawLine(QPointF(x - 4.5, y0 - 2.5), QPointF(x, y0 - 6.5))
        painter.drawLine(QPointF(x + 4.5, y0 - 2.5), QPointF(x, y0 - 6.5))
        painter.drawLine(QPointF(x - 4.5, y0 + 2.5), QPointF(x, y0 + 6.5))
        painter.drawLine(QPointF(x + 4.5, y0 + 2.5), QPointF(x, y0 + 6.5))
    elif kind == "reset":
        # 复位：圆弧 + 箭头（↺ 风格）
        pen.setWidthF(2.4)
        painter.setPen(pen)
        rect = QRectF(x - 6, y0 - 6, 12, 12)
        painter.drawArc(rect, 60 * 16, 260 * 16)
        # 箭头
        painter.drawLine(QPointF(x + 5.8, y0 - 5.2), QPointF(x + 7.6, y0 - 2.4))
        painter.drawLine(QPointF(x + 5.8, y0 - 5.2), QPointF(x + 2.8, y0 - 4.6))


def _kind_for_text(text: str) -> str:
    t = text.strip()
    if t in ("开始同传",):
        return "play"
    if t in ("暂停",):
        return "pause"
    if t in ("继续", "恢复"):
        return "play"
    if t == "交互":
        return "unlock"
    if t == "穿透":
        return "lock"
    if t == "退出":
        return "exit"
    if t == "翻看":
        return "view"
    if t == "复位":
        return "reset"
    return ""


class IconButton(QPushButton):
    """带手绘矢量图标的按钮。图标类型随文字状态自动切换。"""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setText(text)

    def setText(self, text: str):
        super().setText(text)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        kind = _kind_for_text(self.text())
        if not kind:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        _path_icon(self, painter, kind)
        painter.end()
