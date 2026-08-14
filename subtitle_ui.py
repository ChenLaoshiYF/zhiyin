# -*- coding: utf-8 -*-
"""置顶半透明字幕窗 + 控制条（Hanako 暖纸风格 · 精修版）

- 字幕窗：无边框、置顶、暖墨半透明底、圆角阴影；可拖动、右下角可缩放
- 功能键直接覆盖在文本框右上角（暂停/穿透/退出），左上角环形圆标
- 对照字幕：俄文主行 + 中文副行，紧凑排版；滚动查看历史
- 流式草稿：说话中俄文实时更新（partial），定稿后翻译回填（zh）
- 控制条：暂停、翻看、复位、退出；自动隐藏；拖拽整体移动
"""

import html
import queue

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PyQt6.QtGui import QColor, QCursor
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from icons import IconButton
from brand import APP_TITLE, LogoWidget

# 消息协议：("partial", seq, text) 草稿；("ru", seq, text) 定稿；("zh", seq, partial) 译文
MAX_BLOCKS = 300

_SANS = "'Microsoft YaHei UI', 'Microsoft YaHei', 'Segoe UI', sans-serif"
SERIF = _SANS
RU_SERIF = "'Times New Roman', Georgia, serif"

_BTN_OVER = f"""
QPushButton {{ background: #3B372F; color: #EDE6D8; border: 1px solid rgba(255,255,255,0.10);
              border-radius: 12px; padding: 5px 14px 5px 28px; font-size: 12px;
              font-family: {_SANS}; }}
QPushButton:hover {{ background: #537D96; color: #FBF7EE; }}
QPushButton:pressed {{ background: #33536B; }}
"""


def _split_confirmed(old: str, new: str):
    """按词找最长公共前缀，返回 (已确认部分, 待确认尾部)。"""
    old_w = old.split()
    new_w = new.split()
    n = 0
    for a, b in zip(old_w, new_w):
        if a == b:
            n += 1
        else:
            break
    return " ".join(new_w[:n]), " ".join(new_w[n:])


class SubtitleWindow(QWidget):
    def __init__(self, ui_cfg: dict, data_q: queue.Queue, writer=None):
        super().__init__()
        self.data_q = data_q
        self.cfg = ui_cfg
        self.writer = writer  # 文稿计数（控制条并入字幕窗后）
        self.paused = False
        self._pause_cb = None  # 暂停回调（由 main 注入 pipeline.set_paused）
        self.blocks = []
        self._seq_map = {}
        self._ru_text = {}   # seq -> 当前俄文
        self._zh_text = {}   # seq -> 当前中文
        self._last_partial = {}  # seq -> 上一个草稿文本（用于渐进确认）
        self._stick = True
        self._user_resized = False
        self._resize_start = None
        self._docked = True

        self.setWindowTitle(APP_TITLE + " · 字幕")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._ct = bool(ui_cfg.get("click_through", False))

        self.setMinimumWidth(320)
        self.setMinimumHeight(108)  # 顶栏 + 至少一行文字，任何尺寸都能看到字
        self._build_ui()
        self.setWindowOpacity(ui_cfg.get("opacity", 0.95))

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(100)
        # 保持最顶层：定期提升 z-order（不抢焦点）
        self._top_timer = QTimer(self)
        self._top_timer.timeout.connect(self._keep_on_top)
        self._top_timer.start(3000)

    def _keep_on_top(self):
        """强制置顶：Windows 下用 SetWindowPos 提到 TOPMOST 层。"""
        self.raise_()
        try:
            import ctypes
            hwnd = int(self.winId())
            ctypes.windll.user32.SetWindowPos(
                hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)  # TOPMOST, 不移动不缩放不抢焦点
        except Exception:
            pass

    # ---- UI ----
    def _build_ui(self):
        self._fs = self.cfg.get("font_size", 20)       # 俄文主字号
        self._fs_zh = self.cfg.get("font_size_zh", self._fs)  # 中文与俄文同号，对齐

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)  # 阴影留白，紧凑
        outer.setSpacing(0)

        self.card = QWidget()
        self.card.setObjectName("card")
        self.card.setStyleSheet(
            "#card { background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            " stop:0 rgba(46,42,38,215), stop:1 rgba(46,42,38,160));"
            " border-radius: 18px; }"
        )
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(44, 36, 22, 110))
        self.card.setGraphicsEffect(shadow)

        # 紧凑内边距
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(10, 22, 10, 6)  # 顶部仅留功能键空间，压紧
        card_layout.setSpacing(2)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)  # 宽度跟视口，高度自动管理内容
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { background: rgba(255,255,255,0.05); width: 6px;"
            " border-radius: 3px; margin: 2px; }"
            "QScrollBar::handle:vertical { background: rgba(255,255,255,0.22);"
            " border-radius: 3px; min-height: 26px; }"
            "QScrollBar::handle:vertical:hover { background: rgba(83,125,150,0.8); }"
            "QScrollBar::add-line, QScrollBar::sub-line { height: 0; }"
            "QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }"
        )
        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        container_lay = QVBoxLayout(self.container)
        container_lay.setContentsMargins(0, 0, 2, 0)
        container_lay.setSpacing(0)

        # 句子区域：单独 host，高度=内容，永不拉伸
        self.blocks_host = QWidget()
        self.blocks_layout = QVBoxLayout(self.blocks_host)
        self.blocks_layout.setContentsMargins(0, 0, 0, 0)
        self.blocks_layout.setSpacing(0)  # 句子间无空隙
        container_lay.addWidget(self.blocks_host)
        # 末尾弹性：窗口拉高时多余空间全部归 stretch，句子保持原位原高
        container_lay.addStretch(1)
        self.scroll.setWidget(self.container)
        card_layout.addWidget(self.scroll, 1)

        self._placeholder = QLabel("正在监听课堂声音…")
        self._placeholder.setStyleSheet(
            f"color: rgba(245,239,228,0.5); font-size: {self._fs_zh}px;"
            f" font-family: {SERIF}; padding: 4px 2px;"
        )
        self.blocks_layout.addWidget(self._placeholder)

        # 占位文字呼吸闪烁
        self._ph_on = False
        self._breath_timer = QTimer(self)
        self._breath_timer.timeout.connect(self._breath_tick)
        self._breath_timer.start(720)

        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
        outer.addWidget(self.card)

        # 右下角缩放手柄
        self._handle = QLabel("◢")
        self._handle.setFixedSize(16, 16)
        self._handle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._handle.setStyleSheet(
            "color: rgba(245,239,228,0.28); font-size: 9px; background: transparent;"
        )
        self._handle.setCursor(QCursor(Qt.CursorShape.SizeFDiagCursor))
        self._handle.mousePressEvent = self._on_resize_start
        self._handle.mouseMoveEvent = self._on_resize_move
        card_layout.addWidget(self._handle, 0, Qt.AlignmentFlag.AlignRight)

        # 功能键覆盖在文本框上
        self._make_fbuttons()
        self.setStyleSheet(f"QWidget {{ font-family: {SERIF}; }}")
        QTimer.singleShot(0, self._dock_bottom)

    def _breath_tick(self):
        if self._placeholder is None:
            self._breath_timer.stop()
            return
        self._ph_on = not self._ph_on
        a = "0.62" if self._ph_on else "0.36"
        self._placeholder.setStyleSheet(
            f"color: rgba(245,239,228,{a}); font-size: {self._fs_zh}px;"
            f" font-family: {SERIF}; padding: 4px 2px;"
        )

    def _make_fbuttons(self):
        # 纸音徽标：声波 + 纸角，与启动器品牌一致
        self.logo_wrap = LogoWidget(30, self.card)

        self.fbtn_pause = IconButton("暂停")
        self.fbtn_pause.setStyleSheet(_BTN_OVER)
        self.fbtn_pause.clicked.connect(self._on_fpause)
        self.fbtn_pause.setParent(self.card)

        self.fbtn_lock = IconButton("交互")
        self.fbtn_lock.setStyleSheet(_BTN_OVER)
        self.fbtn_lock.setToolTip("当前：可交互。点击切换为穿透（不挡课件）；再点切回")
        self.fbtn_lock.clicked.connect(self._on_flock)
        self.fbtn_lock.setParent(self.card)

        self.fbtn_reset = IconButton("复位")
        self.fbtn_reset.setStyleSheet(_BTN_OVER)
        self.fbtn_reset.setToolTip("回到屏幕底部居中")
        self.fbtn_reset.clicked.connect(self._on_freset)
        self.fbtn_reset.setParent(self.card)

        self.fbtn_quit = IconButton("退出")
        self.fbtn_quit.setStyleSheet(_BTN_OVER)
        self.fbtn_quit.clicked.connect(QApplication.instance().quit)
        self.fbtn_quit.setParent(self.card)

        # 文稿计数：右下角小字
        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet(
            "color: rgba(245,239,228,0.45); font-size: 11px; background: transparent;"
            f" font-family: {_SANS};"
        )
        self.lbl_count.setParent(self.card)
        self._count_timer = QTimer(self)
        self._count_timer.timeout.connect(self._refresh_count)
        self._count_timer.start(2000)

        for b in (self.fbtn_pause, self.fbtn_lock, self.fbtn_reset, self.fbtn_quit):
            b.adjustSize()
        # 穿透提示（在卡片内，穿透时显示）
        self._ct_hint = QLabel("已穿透：点「交互」切回")
        self._ct_hint.setStyleSheet(
            "color: rgba(232,222,204,0.8); font-size: 11px;"
            " background: rgba(42,38,34,0.6); border-radius: 6px; padding: 2px 9px;"
            f" font-family: {_SANS};"
        )
        self._ct_hint.setParent(self.card)
        self._ct_hint.adjustSize()
        self._ct_hint.hide()
        self._place_fbuttons()

    def _place_fbuttons(self):
        if not hasattr(self, "fbtn_quit"):
            return
        m = 6
        y = m
        x = self.card.width() - m
        for b in (self.fbtn_quit, self.fbtn_reset, self.fbtn_lock, self.fbtn_pause):
            b.move(x - b.width(), y)
            x = b.x() - 6
        # 文稿计数：右下角（缩放手柄左侧）
        self.lbl_count.adjustSize()
        self.lbl_count.move(self.card.width() - 30 - self.lbl_count.width(),
                            self.card.height() - 22)
        self.logo_wrap.move(m, y)
        # 穿透提示：按钮下方
        self._ct_hint.move((self.card.width() - self._ct_hint.width()) // 2, y + 32)

    def _refresh_count(self):
        if self.writer and self.writer.enabled:
            self.lbl_count.setText(f"文稿 {self.writer.count} 条")
        else:
            self.lbl_count.setText("")

    # ---- 拖动 ----
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and hasattr(self, "_drag_pos"):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    # ---- 缩放 ----
    def _on_resize_start(self, event):
        self._resize_start = (event.globalPosition().toPoint(), self.width(), self.height())

    def _on_resize_move(self, event):
        if self._resize_start is None:
            return
        start_pt, w0, h0 = self._resize_start
        delta = event.globalPosition().toPoint() - start_pt
        self.setFixedSize(max(320, w0 + delta.x()), max(108, h0 + delta.y()))
        self._user_resized = True
        self._place_fbuttons()

    # ---- 数据 ----
    def _poll(self):
        try:
            while True:
                kind, seq, text = self.data_q.get_nowait()
                if kind == "partial":
                    self._handle_partial(seq, text)
                elif kind == "ru":
                    self._add_ru(seq, text)
                elif kind == "zh":
                    self._update_zh(seq, text)
        except queue.Empty:
            pass

    def _line_html(self, ru, zh):
        """单行混排：俄文在前（浅色），中文紧接（亮色）。外层 p margin/padding 归零，
        消除 QLabel 富文本默认段落边距（句间空隙的来源）。"""
        esc = html.escape
        ru_html = (f'<span style="color:#E8DEC8; font-size:{self._fs}px; '
                   f'font-family:{RU_SERIF};">{esc(ru)}</span>')
        if zh:
            zh_html = (f'<span style="color:#F5EFE4; font-size:{self._fs_zh}px; '
                       f'font-weight:500; font-family:{SERIF};"> {esc(zh)}</span>')
            return f'<p style="margin:0; padding:0; line-height:120%;">{ru_html}{zh_html}</p>'
        return f'<p style="margin:0; padding:0; line-height:120%;">{ru_html}</p>'

    def _create_block(self, seq, ru_text):
        """新建一个句子块：俄文+中文同一行，左对齐，句间无空隙。"""
        block = QWidget()
        bl = QVBoxLayout(block)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)

        label = QLabel()
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        # 水平 Ignored：宽度完全交给布局（容器宽），长句在行内换行，绝不右裁
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        label.setMinimumHeight(22)  # 任何窗口尺寸下至少能显示一行文字
        label.setText(self._line_html(ru_text, None))
        effect = QGraphicsOpacityEffect(label)
        effect.setOpacity(1.0)
        label.setGraphicsEffect(effect)

        bl.addWidget(label)
        self.blocks_layout.addWidget(block)
        self.blocks.append(block)
        self._seq_map[seq] = (label, effect)
        self._ru_text[seq] = ru_text

        if len(self.blocks) > MAX_BLOCKS:
            old = self.blocks.pop(0)
            self.blocks_layout.removeWidget(old)
            old.deleteLater()

        self._fade_in(block)
        return label, effect

    def _handle_partial(self, seq, text):
        """草稿：渐进确认 + 渐变过渡。窗口大小不变（不跳），文字柔和变化。"""
        entry = self._seq_map.get(seq)
        if entry is None:
            label, effect = self._create_block(seq, text)
            self._last_partial[seq] = text
        else:
            label, effect = entry
            prev = self._last_partial.get(seq, "")
            confirmed, pending = _split_confirmed(prev, text)
            self._last_partial[seq] = text
            self._ru_text[seq] = text
            esc = html.escape
            if pending:
                label.setText(
                    f'<p style="margin:0; padding:0; line-height:120%;">'
                    f'<span style="color:#F5F0E4; font-size:{self._fs}px; '
                    f'font-family:{RU_SERIF};">{esc(confirmed)}</span>'
                    f'<span style="color:rgba(232,222,204,0.42);font-style:italic; '
                    f'font-size:{self._fs}px; font-family:{RU_SERIF};">{esc(pending)}</span>'
                    f'</p>'
                )
            else:
                label.setText(
                    f'<p style="margin:0; padding:0; line-height:120%;">'
                    f'<span style="color:#F5F0E4; font-size:{self._fs}px; '
                    f'font-family:{RU_SERIF};">{esc(text)}</span>'
                    f'</p>'
                )
            # 渐变过渡：文字变化柔和不闪
            anim = QPropertyAnimation(effect, b"opacity", label)
            anim.setDuration(220)
            anim.setStartValue(0.45)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.start()
        # 草稿阶段不改变窗口尺寸（避免跳动），只跟随滚动
        if self._stick:
            QTimer.singleShot(0, self._scroll_to_bottom)

    def _add_ru(self, seq, text):
        if self._placeholder is not None:
            self._placeholder.hide()  # 立即隐藏，不等 deleteLater 销毁
            self.blocks_layout.removeWidget(self._placeholder)
            self._placeholder.deleteLater()
            self._placeholder = None
        self._ru_text[seq] = text
        entry = self._seq_map.get(seq)
        if entry is None:
            label, effect = self._create_block(seq, text)
        else:
            label, effect = entry
            label.setText(self._line_html(text, self._zh_text.get(seq)))
        self._last_partial.pop(seq, None)
        self._after_content_change()

    def _update_zh(self, seq, text):
        entry = self._seq_map.get(seq)
        if entry is not None:
            label, effect = entry
            self._zh_text[seq] = text
            label.setText(self._line_html(self._ru_text.get(seq, ""), text))

    def _after_content_change(self):
        if not self._user_resized:
            # 等布局先激活（换行高度计算完成）再调窗口尺寸
            QTimer.singleShot(0, self._fit_and_resize)
        if self._stick:
            QTimer.singleShot(0, self._scroll_to_bottom)

    def _fit_and_resize(self):
        if self._user_resized:
            return
        self._fit_width()
        self._resize_to_fit()

    def _fit_width(self):
        """窗口宽度固定：所有句子同宽显示、换行一致，规整不跳动。"""
        if self._user_resized or getattr(self, "_width_fixed", False):
            return
        w = int(self.cfg.get("width", 720))
        self.setFixedSize(w, self.height())
        self._width_fixed = True
        self._place_fbuttons()

    # ---- 滚动 ----
    def _on_scroll(self, value):
        bar = self.scroll.verticalScrollBar()
        self._stick = value >= bar.maximum() - 30

    def moveEvent(self, event):
        super().moveEvent(event)
        self._place_fbuttons()

    def resizeEvent(self, event):
        """缩放时容器宽度跟随视口，防止文字溢出块外；缩放后回到最新句。"""
        super().resizeEvent(event)
        vp = self.scroll.viewport()
        if self.container.width() != vp.width():
            self.container.setFixedWidth(vp.width())
        self._place_fbuttons()
        # 缩放后内容重排，强制回到最新句（防止停在空白/旧位置）
        self._stick = True
        QTimer.singleShot(30, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
        QTimer.singleShot(30, lambda: bar.setValue(bar.maximum()))

    def _resize_to_fit(self):
        h = self.container.sizeHint().height() + 56
        max_h = int(QApplication.primaryScreen().availableGeometry().height() * 0.45)
        # 有内容时至少显示 4 个句块的高度，无内容保持紧凑
        floor = 240 if self.blocks else 130
        new_h = min(max(h, floor), max_h)
        if self.height() != new_h:
            self.setFixedSize(self.width(), new_h)
        if self._docked and not getattr(self, "_moved", False):
            screen = QApplication.primaryScreen().availableGeometry()
            x = screen.center().x() - self.width() // 2
            y = screen.bottom() - self.height() - 84
            self.move(x, y)

    def _dock_bottom(self):
        self._resize_to_fit()
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.center().x() - self.width() // 2
        y = screen.bottom() - self.height() - 84
        self.move(x, y)
        self._docked = True
        self._place_fbuttons()

    # ---- 特效 ----
    def _fade_in(self, widget):
        eff = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", widget)
        anim.setDuration(320)
        anim.setStartValue(0.35)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()

    # ---- 模式 - 穿透机制 ----
    def set_pause_callback(self, cb):
        self._pause_cb = cb

    def _on_fpause(self):
        self.paused = not self.paused
        self.fbtn_pause.setText("继续" if self.paused else "暂停")
        if self._pause_cb:
            self._pause_cb(self.paused)

    def _on_flock(self):
        self.set_click_through(not self._ct)

    def _on_freset(self):
        self._moved = False
        self._docked = True
        self._dock_bottom()

    def _hit_rect_physical(self):
        """可交互区域（4 个按钮排 + 提示）在屏幕上的物理像素矩形。
        穿透模式下只有这个区域能点，其余区域鼠标直接穿到下层。
        """
        from PyQt6.QtCore import QPoint, QRect
        p1 = self.fbtn_pause.mapTo(self, self.fbtn_pause.rect().topLeft())
        p2 = self.fbtn_quit.mapTo(self, self.fbtn_quit.rect().bottomRight())
        g1 = self.mapToGlobal(p1)
        g2 = self.mapToGlobal(p2)
        dpr = self.devicePixelRatioF()
        return QRect(int(g1.x() * dpr), int(g1.y() * dpr),
                     int((g2.x() - g1.x()) * dpr), int((g2.y() - g1.y()) * dpr))

    def hit_test_transparent(self, phys_x: int, phys_y: int) -> bool:
        """穿透模式下：给定屏幕物理坐标，返回该点是否应穿透（True=穿透）。
        按钮区永不穿透，保证「交互/穿透」一直能点。
        """
        if not self._ct:
            return False
        r = self._hit_rect_physical()
        return not r.contains(phys_x, phys_y)

    def set_click_through(self, enabled: bool):
        """切换穿透/交互。穿透只作用于内容区（WM_NCHITTEST 逐点判断），
        按钮区一直可点，不依赖热键。
        """
        self._ct = enabled
        self.fbtn_lock.setText("穿透" if enabled else "交互")
        self.fbtn_lock.setToolTip("已穿透：内容区点不到，按钮区仍可点，点这里切回"
                                  if enabled else "当前：可交互。点击切换为穿透（不挡课件）")
        self._ct_hint.setVisible(enabled)
        if enabled:
            self._place_fbuttons()

    def toggle_pause(self):
        self.paused = not self.paused
        return self.paused

    def toggle_visible(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()

    def closeEvent(self, event):
        QApplication.instance().quit()
        event.accept()

