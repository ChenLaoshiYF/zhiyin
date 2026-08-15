# -*- coding: utf-8 -*-
"""俄汉同传 启动器（Hanako 暖纸风格 · 精修版）

无边框窗口：顶部品牌区拖动，右下角缩放手柄缩放。
双击「启动俄汉同传.vbs」打开本窗口。

精修要点：
- 图标：环形双圈圆形徽标，替代原来生硬的方块
- 云端表单可折叠：选「本地」时不显示灰掉的云端字段，界面清爽
- 统一卡片阴影与字体，退出键改幽灵样式
"""

import datetime
import json
import os
import subprocess
import sys
import threading

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFormLayout,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QRadioButton, QSizeGrip, QSlider,
    QVBoxLayout, QWidget,
)

from icons import IconButton
from brand import APP_NAME, APP_SLOGAN, APP_TITLE, LogoWidget

PROJECT_DIR = (os.path.dirname(os.path.abspath(sys.executable))
               if getattr(sys, "frozen", False)
               else os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_DIR, "config.json")
VENV_PYTHONW = os.path.join(PROJECT_DIR, ".venv", "Scripts", "pythonw.exe")
LOCK_PATH = os.path.join(PROJECT_DIR, "app.lock")

# ---- Hanako 暖纸风格 · 精修版 ----
# 正文字体用微软雅黑（现代干净），俄文/预览保留衬线
_SANS = "'Microsoft YaHei UI', 'Microsoft YaHei', 'Segoe UI', sans-serif"

PAPER_QSS = f"""
QWidget {{ background-color: transparent; color: #3C3833;
          font-family: {_SANS}; font-size: 13px; }}
QWidget#root {{ border: none; }}
QPushButton#winBtn, QPushButton#winBtnClose {{ background: transparent; color: #8A8176; border: none;
    border-radius: 8px; font-size: 13px; font-family: {_SANS}; }}
QPushButton#winBtn:hover {{ background: rgba(83,125,150,0.14); color: #33536B; }}
QPushButton#winBtnClose:hover {{ background: #C4594E; color: #FFFFFF; }}
QGroupBox {{ border: 0.5px solid rgba(83,125,150,0.16); border-radius: 16px;
            margin-top: 16px; padding: 14px 16px 12px 16px;
            background: rgba(255,255,255,0.60); }}
QGroupBox::title {{ subcontrol-origin: margin; left: 20px; padding: 0 8px;
                   color: #8A8176; font-size: 11px; letter-spacing: 3px;
                   border-left: 3px solid rgba(83,125,150,0.6); }}
QLineEdit, QComboBox {{ background: rgba(255,255,255,0.92); border: 1px solid #E4DED2;
                       border-radius: 10px; padding: 7px 12px; selection-background-color: #537D96;
                       selection-color: #FBF7EE; color: #2C2823; }}
QLineEdit:focus, QComboBox:focus {{ border-color: rgba(83,125,150,0.6);
                                   background: #FFFFFF; }}
QLineEdit:disabled, QComboBox:disabled {{ color: #B5AE9E; background: rgba(240,236,226,0.6); }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ image: none; border-left: 4px solid transparent;
                        border-right: 4px solid transparent;
                        border-top: 5px solid #A89F8E; margin-right: 10px; }}
QComboBox QAbstractItemView {{ background: #FEFDF9;
    border: 1px solid #E4DED2; border-radius: 10px; padding: 5px;
    selection-background-color: rgba(83,125,150,0.2); selection-color: #2C2823;
    outline: none; }}
QRadioButton, QCheckBox {{ spacing: 10px; padding: 4px 2px; }}
QRadioButton {{ color: #5F5A52; }}
QRadioButton:checked {{ color: #2C2823; font-weight: 600; }}
QCheckBox {{ color: #5F5A52; }}
QCheckBox:checked {{ color: #2C2823; }}
QRadioButton::indicator, QCheckBox::indicator {{ width: 18px; height: 18px; }}
QRadioButton::indicator {{ border-radius: 9px; border: 1.5px solid #C9BFAB;
                          background: rgba(255,255,255,0.95); }}
QRadioButton::indicator:hover {{ border-color: #537D96; }}
QRadioButton::indicator:checked {{ border: 5.5px solid #537D96; background: #E4ECF5; }}
QCheckBox::indicator {{ border-radius: 5px; border: 1.5px solid #C9BFAB;
                       background: rgba(255,255,255,0.95); }}
QCheckBox::indicator:hover {{ border-color: #537D96; }}
QCheckBox::indicator:checked {{ border-color: #537D96;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #6D9AB8, stop:1 #41698A); }}
QPushButton {{ background: rgba(60,56,51,0.05); border: none; border-radius: 10px;
              padding: 9px 20px 9px 20px; color: #5F5A52; }}
QPushButton:hover {{ background: rgba(83,125,150,0.18); color: #2C2823; }}
QPushButton#backendCard {{ background: rgba(255,255,255,0.78); border: 1.5px solid #E4DED2;
    border-radius: 14px; padding: 10px 14px; color: #6A6358; font-size: 13px; }}
QPushButton#backendCard:hover {{ border-color: rgba(83,125,150,0.5); color: #2C2823; }}
QPushButton#backendCard:checked {{ background: rgba(83,125,150,0.14);
    border-color: #537D96; color: #2E4F66; font-weight: 600; }}
QLabel#valueBadge {{ background: rgba(83,125,150,0.12); color: #33536B;
    border-radius: 9px; padding: 2px 10px; font-size: 12px; font-weight: 600; }}
QLabel#statusCapsule {{ background: rgba(74,107,74,0.10); color: #4A6B4A;
    border-radius: 11px; padding: 5px 14px; font-size: 12px; }}
QPushButton#primary {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
    stop:0 #557D97, stop:1 #33536B); color: #FBF7EE; font-size: 15px;
    font-weight: 600; letter-spacing: 2px; padding: 13px 26px; border-radius: 22px; }}
QPushButton#primary:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
    stop:0 #648EA9, stop:1 #3E6078); }}
QPushButton#ghost {{ background: transparent; border: 1px solid rgba(83,125,150,0.3);
                    color: #7A7366; }}
QPushButton#ghost:hover {{ background: rgba(83,125,150,0.1); color: #33536B;
                          border-color: rgba(83,125,150,0.5); }}
QSlider::groove:horizontal {{ height: 4px; background: rgba(60,56,51,0.12);
                             border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
                             background: #FFFFFF; border: 1px solid rgba(83,125,150,0.45); }}
QSlider::handle:horizontal:hover {{ background: #F0F6FA; border-color: #537D96; }}
QSlider::sub-page:horizontal {{ background: #537D96; border-radius: 2px; }}
"""

FONT_LEVELS = [(14, "小"), (18, "标准"), (22, "大"), (26, "特大"), (30, "最大")]


def _font_level(v):
    for lo, name in FONT_LEVELS:
        if v <= lo + 1:
            return name
    return "最大"


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def add_shadow(widget, blur=26, dy=4, alpha=45):
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, dy)
    shadow.setColor(QColor(60, 52, 38, alpha))
    widget.setGraphicsEffect(shadow)


def _instance_running() -> bool:
    if not os.path.exists(LOCK_PATH):
        return False
    try:
        with open(LOCK_PATH, "r") as f:
            pid = int(f.read().strip())
    except Exception:
        return False
    import ctypes
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if h:
        ctypes.windll.kernel32.CloseHandle(h)
        return True
    return False


class Launcher(QWidget):
    ollama_detected = pyqtSignal(bool, list)
    cloud_models_detected = pyqtSignal(bool, list, str)

    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.setObjectName("root")
        self.setWindowTitle(APP_TITLE + " 启动器")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)  # 背景由 paintEvent 自绘
        self.setMinimumSize(500, 520)
        self.ollama_detected.connect(self._on_ollama_detected)
        self.cloud_models_detected.connect(self._on_cloud_models_detected)
        self._build_ui()
        self._apply_cfg()
        self._breath = None
        threading.Thread(target=self._probe_ollama, daemon=True).start()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 14, 24, 14)
        root.setSpacing(10)

        # ---- 品牌区（兼作拖动柄） ----
        head = QWidget()
        head.setCursor(Qt.CursorShape.OpenHandCursor)
        head.mousePressEvent = self._on_head_press
        head.mouseMoveEvent = self._on_head_move
        head_layout = QHBoxLayout(head)
        head_layout.setContentsMargins(2, 2, 2, 2)
        head_layout.setSpacing(14)

        head_layout.addWidget(LogoWidget(44))

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel(APP_NAME)
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #262220;")
        sub = QLabel(APP_SLOGAN)
        sub.setStyleSheet("color: #8A8176; font-size: 12px;")
        title_box.addWidget(title)
        title_box.addWidget(sub)
        head_layout.addLayout(title_box)
        head_layout.addStretch(1)

        # ---- 窗口控制三键：最小化 / 最大化 / 关闭 ----
        self.btn_min = QPushButton("─")
        self.btn_min.setObjectName("winBtn")
        self.btn_min.setFixedSize(30, 26)
        self.btn_min.setToolTip("最小化")
        self.btn_min.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_min.clicked.connect(self.showMinimized)
        self.btn_max = QPushButton("□")
        self.btn_max.setObjectName("winBtn")
        self.btn_max.setFixedSize(30, 26)
        self.btn_max.setToolTip("最大化 / 还原")
        self.btn_max.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_max.clicked.connect(self._toggle_max)
        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("winBtnClose")
        self.btn_close.setFixedSize(30, 26)
        self.btn_close.setToolTip("退出")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.close)
        head_layout.addWidget(self.btn_min)
        head_layout.addWidget(self.btn_max)
        head_layout.addWidget(self.btn_close)
        root.addWidget(head)

        # ---- 翻译后端 ----
        box = QGroupBox("翻译后端")
        bl = QVBoxLayout(box)
        bl.setSpacing(6)

        # 两张卡片单选：本地 / 云端
        card_row = QHBoxLayout()
        card_row.setSpacing(10)
        self.btn_local = QPushButton("本地 Ollama\n不花钱 · 不联网")
        self.btn_cloud = QPushButton("云端 API\n更快 · 更准")
        for b in (self.btn_local, self.btn_cloud):
            b.setObjectName("backendCard")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        grp = QButtonGroup(self)
        grp.setExclusive(True)
        grp.addButton(self.btn_local)
        grp.addButton(self.btn_cloud)
        self.btn_fast = QRadioButton("极速")
        self.btn_fast.setToolTip("专用翻译 API，响应最快（百兆/免费）")
        grp.addButton(self.btn_fast)
        self.btn_nllb = QRadioButton("本地")
        self.btn_nllb.setToolTip("NLLB 本地翻译，毫秒级、完全离线")
        grp.addButton(self.btn_nllb)
        self.btn_local.setChecked(True)
        card_row.addWidget(self.btn_local, 1)
        card_row.addWidget(self.btn_nllb, 1)
        card_row.addWidget(self.btn_cloud, 1)
        card_row.addWidget(self.btn_fast, 1)
        bl.addLayout(card_row)

        # 本地 NLLB 面板
        self.panel_nllb = QWidget()
        pn = QHBoxLayout(self.panel_nllb)
        pn.setContentsMargins(6, 2, 0, 0)
        self.lbl_nllb_state = QLabel("NLLB 模型：检测中…")
        self.lbl_nllb_state.setStyleSheet("color:#7A7366; font-size:12px;")
        pn.addWidget(self.lbl_nllb_state)
        bl.addWidget(self.panel_nllb)

        # 独立开关：云端修正
        self.chk_refine = QCheckBox("云端修正（本地草稿 + 云端大模型润色）")
        self.chk_refine.setToolTip("勾选后：本地翻译先出草稿（毫秒级），云端大模型再修正润色")
        self.chk_refine.setChecked(True)
        bl.addWidget(self.chk_refine)

        # 本地面板：一行，模型 + 状态
        self.panel_local = QWidget()
        pl = QHBoxLayout(self.panel_local)
        pl.setContentsMargins(6, 2, 0, 0)
        pl.setSpacing(8)
        pl.addWidget(QLabel("模型:"))
        self.combo_model = QComboBox()
        self.combo_model.setEditable(True)
        self.combo_model.addItem("qwen3.5:9b")
        pl.addWidget(self.combo_model, 1)
        self.lbl_ollama_state = QLabel("正在找 Ollama…")
        self.lbl_ollama_state.setStyleSheet("color:#7A7366; font-size:12px;")
        pl.addWidget(self.lbl_ollama_state)
        bl.addWidget(self.panel_local)

        bl.addSpacing(2)

        # 云端面板：可折叠
        self.panel_cloud = QWidget()
        form = QFormLayout(self.panel_cloud)
        form.setContentsMargins(6, 2, 0, 0)
        form.setSpacing(6)
        self.edit_base = QLineEdit()
        self.edit_base.setPlaceholderText("https://api.deepseek.com")
        self.edit_key = QLineEdit()
        self.edit_key.setPlaceholderText("sk-...")
        self.edit_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_model = QComboBox()
        self.edit_model.setEditable(True)
        self.edit_model.setPlaceholderText("填模型名，或点右侧自动列出")
        self.btn_detect = QPushButton("检测模型")
        self.btn_detect.setObjectName("ghost")
        self.btn_detect.setStyleSheet("padding:5px 12px; font-size:12px;")
        self.btn_detect.clicked.connect(self.on_detect_models)
        model_row = QHBoxLayout()
        model_row.setSpacing(8)
        model_row.addWidget(self.edit_model, 1)
        model_row.addWidget(self.btn_detect)
        self.lbl_detect_state = QLabel("")
        self.lbl_detect_state.setStyleSheet("color:#7A7366; font-size:11px;")
        form.addRow("API 地址:", self.edit_base)
        form.addRow("API Key:", self.edit_key)
        form.addRow("模型:", model_row)
        form.addRow("", self.lbl_detect_state)
        bl.addWidget(self.panel_cloud)

        # 极速面板：专用翻译 API
        self.panel_fast = QWidget()
        ff = QFormLayout(self.panel_fast)
        ff.setContentsMargins(6, 2, 0, 0)
        ff.setSpacing(6)
        self.combo_fast_provider = QComboBox()
        self.combo_fast_provider.addItem("MyMemory（免 key）", "mymemory")
        self.combo_fast_provider.addItem("百度翻译（需 appid）", "baidu")
        self.combo_fast_provider.currentIndexChanged.connect(self._toggle_fast_provider)
        ff.addRow("服务:", self.combo_fast_provider)
        self.edit_baidu_appid = QLineEdit()
        self.edit_baidu_appid.setPlaceholderText("百度翻译开放平台 appid")
        self.edit_baidu_secret = QLineEdit()
        self.edit_baidu_secret.setPlaceholderText("百度翻译 secret")
        self.edit_baidu_secret.setEchoMode(QLineEdit.EchoMode.Password)
        ff.addRow("AppID:", self.edit_baidu_appid)
        ff.addRow("Secret:", self.edit_baidu_secret)
        self.lbl_fast_hint = QLabel("MyMemory 免费免注册；百度需在 fanyi-api.baidu.com 免费注册")
        self.lbl_fast_hint.setStyleSheet("color:#7A7366; font-size:11px;")
        ff.addRow("", self.lbl_fast_hint)
        bl.addWidget(self.panel_fast)

        self.btn_local.toggled.connect(self._toggle_backend)
        add_shadow(box, blur=16, dy=3, alpha=42)
        root.addWidget(box)

        # ---- 字幕样式 ----
        style_box = QGroupBox("字幕样式")
        sl = QVBoxLayout(style_box)
        sl.setSpacing(5)

        fs_row = QHBoxLayout()
        fs_row.addWidget(QLabel("俄文字号"))
        self.slider_font = QSlider(Qt.Orientation.Horizontal)
        self.slider_font.setRange(14, 32)
        self.slider_font.setTickPosition(QSlider.TickPosition.NoTicks)
        self.lbl_font_val = QLabel("20px · 标准")
        self.lbl_font_val.setObjectName("valueBadge")
        self.lbl_font_val.setMinimumWidth(64)
        self.lbl_font_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.slider_font.valueChanged.connect(self._on_font_changed)
        fs_row.addWidget(self.slider_font, 1)
        fs_row.addWidget(self.lbl_font_val)
        sl.addLayout(fs_row)

        ruler = QHBoxLayout()
        ruler.setContentsMargins(0, 0, 0, 0)
        ruler.setSpacing(0)
        for i, (v, name) in enumerate(FONT_LEVELS):
            label = QLabel(name)
            label.setStyleSheet("color:#AAA395; font-size:10.5px;")
            if i == 0:
                label.setAlignment(Qt.AlignmentFlag.AlignLeft)
            elif i == len(FONT_LEVELS) - 1:
                label.setAlignment(Qt.AlignmentFlag.AlignRight)
            else:
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setProperty("level", name)
            ruler.addWidget(label, 1)
        sl.addLayout(ruler)
        self._ruler_labels = [ruler.itemAt(i).widget() for i in range(ruler.count())]

        op_row = QHBoxLayout()
        op_row.addWidget(QLabel("底衬深浅"))
        self.slider_opacity = QSlider(Qt.Orientation.Horizontal)
        self.slider_opacity.setRange(40, 100)
        self.lbl_opacity_val = QLabel("90%")
        self.lbl_opacity_val.setObjectName("valueBadge")
        self.lbl_opacity_val.setMinimumWidth(64)
        self.lbl_opacity_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.slider_opacity.valueChanged.connect(self._on_opacity_changed)
        op_row.addWidget(self.slider_opacity, 1)
        op_row.addWidget(self.lbl_opacity_val)
        sl.addLayout(op_row)

        # 字幕实时预览：俄文大 + 中文小，对照排版
        self.preview_box = QWidget()
        preview_lay = QVBoxLayout(self.preview_box)
        preview_lay.setContentsMargins(14, 10, 14, 10)
        preview_lay.setSpacing(3)
        self.preview_ru = QLabel("Квадратное уравнение имеет два корня.")
        self.preview_ru.setStyleSheet(
            "color:#E9DFC9; font-size:20px; font-family: 'Times New Roman', Georgia, serif;"
        )
        self.preview_ru.setWordWrap(True)
        self.preview_zh = QLabel("二次方程有两个根。")
        self.preview_zh.setStyleSheet(
            "color:#F5EFE4; font-size:20px; font-weight:500;"
            f" font-family: {_SANS};"
        )
        preview_lay.addWidget(self.preview_ru)
        preview_lay.addWidget(self.preview_zh)
        self.preview_box.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            " stop:0 rgba(45,41,36,200), stop:1 rgba(45,41,36,150));"
            " border-radius: 14px;"
        )
        add_shadow(self.preview_box, blur=18, dy=4, alpha=55)
        sl.addWidget(self.preview_box)
        add_shadow(style_box, blur=16, dy=3, alpha=42)
        root.addWidget(style_box)

        # ---- 课堂记录 ----
        box2 = QGroupBox("课堂记录")
        b2 = QVBoxLayout(box2)
        b2.setSpacing(8)
        self.chk_transcript = QCheckBox("把课堂记下来（俄中双语，Markdown）")
        self.chk_transcript.toggled.connect(self._update_transcript_preview)
        b2.addWidget(self.chk_transcript)

        dir_row = QHBoxLayout()
        dir_row.setSpacing(6)
        self.edit_dir = QLineEdit()
        self.edit_dir.setPlaceholderText("文稿（项目内，默认）")
        self.edit_dir.setToolTip("可直接输入保存路径，也可以点右侧按钮选择文件夹")
        self.edit_dir.setMinimumHeight(30)
        self.edit_dir.setStyleSheet(
            "padding: 3px 10px; border-radius: 8px;"
            " border: 1px solid rgba(83,125,150,0.18);"
            " background: rgba(255,255,255,0.55);"
        )
        self.btn_browse = QPushButton("选择文件夹…")
        self.btn_browse.setObjectName("ghost")
        self.btn_browse.setMinimumHeight(30)
        self.btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse.clicked.connect(self.on_browse_dir)
        dir_row.addWidget(self.edit_dir, 1)
        dir_row.addWidget(self.btn_browse, 0)
        b2.addLayout(dir_row)
        add_shadow(box2, blur=16, dy=3, alpha=42)
        root.addWidget(box2)

        # ---- 按钮 ----
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.btn_start = QPushButton("开始同传")
        self.btn_start.setObjectName("primary")
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.clicked.connect(self.on_start)
        add_shadow(self.btn_start, blur=22, dy=4, alpha=80)
        self.btn_quit = IconButton("退出")
        self.btn_quit.setObjectName("ghost")
        self.btn_quit.setStyleSheet("padding: 9px 20px 9px 34px;")
        self.btn_quit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_quit.clicked.connect(QApplication.instance().quit)
        btn_row.addWidget(self.btn_start, 3)
        btn_row.addWidget(self.btn_quit, 1)
        root.addLayout(btn_row)

        self.lbl_status = QLabel("●  一切就绪")
        self.lbl_status.setObjectName("statusCapsule")
        self.lbl_status.setStyleSheet("color:#4A6B4A;")
        root.addWidget(self.lbl_status, 0, Qt.AlignmentFlag.AlignLeft)

        # 右下角缩放手柄
        grip = QSizeGrip(self)
        grip.setStyleSheet("background: transparent;")
        root.addWidget(grip, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)

        self._attach_select_effects()
        self._toggle_backend()
        self._update_transcript_preview()
        self._check_nllb()

    # ---- 窗口拖动 ----
    def paintEvent(self, event):
        """自绘背景：暖纸渐变 + 圆角 + 描边。不依赖 QSS，透明窗口下也稳定显示。"""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, QColor(253, 251, 245))
        grad.setColorAt(0.45, QColor(248, 242, 232))
        grad.setColorAt(1.0, QColor(240, 233, 220))
        p.setBrush(grad)
        p.setPen(QPen(QColor(83, 125, 150, 60), 1))
        p.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, 20, 20)

    def _toggle_max(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _on_head_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def _on_head_move(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and hasattr(self, "_drag_pos"):
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    # ---- 窗口淡入 ----
    def showEvent(self, event):
        super().showEvent(event)
        self.setWindowOpacity(0.0)
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(380)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._enter_anim = anim

    # ---- 选择项特效 ----
    def _attach_select_effects(self):
        self.chk_transcript.toggled.connect(lambda checked: self._pulse(self.chk_transcript) if checked else None)

    def _pulse(self, widget):
        eff = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", widget)
        anim.setDuration(220)
        anim.setStartValue(0.55)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()

    # ---- 后端切换 ----
    def _toggle_backend(self):
        self.panel_local.setVisible(self.btn_local.isChecked())
        self.panel_nllb.setVisible(self.btn_nllb.isChecked())
        self.panel_cloud.setVisible(self.btn_cloud.isChecked())
        self.panel_fast.setVisible(self.btn_fast.isChecked())
        if self.btn_cloud.isChecked():
            self.lbl_detect_state.setText("")
        QTimer.singleShot(0, self._fit_height)

    def _check_nllb(self):
        """检查本地 NLLB 模型是否就绪。"""
        model_dir = os.path.join(PROJECT_DIR, "models", "nllb-200-distilled-600M")
        ready = os.path.isfile(os.path.join(model_dir, "pytorch_model.bin"))
        self.lbl_nllb_state.setText(
            "NLLB 模型：已就绪（毫秒级离线翻译）" if ready
            else "NLLB 模型未下载：联网后运行 download_nllb.py 自动下载（2.3GB）"
        )
        self.lbl_nllb_state.setStyleSheet(
            "color:#4A6B4A; font-size:12px;" if ready
            else "color:#8B7A5C; font-size:12px;"
        )

    def _toggle_fast_provider(self):
        """极速服务切换：百度才需要 appid/secret。"""
        is_baidu = self.combo_fast_provider.currentData() == "baidu"
        self.edit_baidu_appid.setEnabled(is_baidu)
        self.edit_baidu_secret.setEnabled(is_baidu)

    def _fit_height(self):
        """窗口高度贴合当前内容（云端表单展开时更高）。"""
        h = self.layout().sizeHint().height()
        self.resize(self.width(), min(max(h + 24, 520), 900))

    # ---- 字号与刻度 ----
    def _on_font_changed(self, v):
        level = _font_level(v)
        self.lbl_font_val.setText(f"{v}px · {level}")
        # 与字幕窗一致：俄汉同号
        self.preview_ru.setStyleSheet(
            f"color:#E9DFC9; font-size:{v}px;"
            " font-family: 'Times New Roman', Georgia, serif;"
        )
        self.preview_zh.setStyleSheet(
            f"color:#F5EFE4; font-size:{v}px; font-weight:500;"
            f" font-family: {_SANS};"
        )
        for lbl in self._ruler_labels:
            lbl.setStyleSheet(
                "color:#2C2823; font-size:10.5px; font-weight:600;"
                if lbl.property("level") == level
                else "color:#AAA395; font-size:10.5px;"
            )

    def _on_opacity_changed(self, v):
        self.lbl_opacity_val.setText(f"{v}%")

    # ---- 配置回填 ----
    def _apply_cfg(self):
        t = self.cfg.get("translate", {})
        cloud = t.get("cloud", {})
        fast = t.get("fast", {})
        backend = t.get("backend", "cloud")
        if backend in ("local", "hybrid"):
            # hybrid = 本地 NLLB 草稿 + 云端修正，选「本地」卡片（对应同款毫秒级草稿）
            self.btn_nllb.setChecked(True)
        elif backend == "fast":
            self.btn_fast.setChecked(True)
            idx = self.combo_fast_provider.findData(fast.get("provider", "mymemory"))
            if idx >= 0:
                self.combo_fast_provider.setCurrentIndex(idx)
            self.edit_baidu_appid.setText(fast.get("appid", ""))
            self.edit_baidu_secret.setText(fast.get("secret", ""))
        elif cloud.get("provider") == "ollama":
            self.btn_local.setChecked(True)
            if cloud.get("model"):
                idx = self.combo_model.findText(cloud["model"])
                if idx >= 0:
                    self.combo_model.setCurrentIndex(idx)
                else:
                    self.combo_model.setCurrentText(cloud["model"])
        else:
            self.btn_cloud.setChecked(True)
            self.edit_base.setText(cloud.get("base_url", ""))
            self.edit_key.setText(cloud.get("api_key", ""))
            if cloud.get("model"):
                self.edit_model.setCurrentText(cloud["model"])
        self.chk_transcript.setChecked(self.cfg.get("save_transcript", True))
        self.chk_refine.setChecked(t.get("refine", True))
        ui = self.cfg.get("ui", {})
        self.slider_font.setValue(int(ui.get("font_size", 20)))
        self.slider_opacity.setValue(int(ui.get("opacity", 0.9) * 100))
        tdir = self.cfg.get("transcript_dir", "文稿")
        if tdir != "文稿":
            self.edit_dir.setText(tdir)
        self._toggle_fast_provider()

    # ---- Ollama 探测 ----
    def _probe_ollama(self):
        try:
            import requests
            r = requests.get("http://localhost:11434/api/tags", timeout=3)
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                self.ollama_detected.emit(True, models)
            else:
                self.ollama_detected.emit(False, [])
        except Exception:
            self.ollama_detected.emit(False, [])

    def _on_ollama_detected(self, ok, models):
        if ok:
            self.combo_model.clear()
            self.combo_model.addItems(models)
            self._set_ollama_state("Ollama 在线", "#4A6B4A", pulse=True)
        else:
            self._set_ollama_state("没找到 Ollama", "#8B2C1F")

    def _set_ollama_state(self, text, color, pulse=False):
        self.lbl_ollama_state.setText(text)
        self.lbl_ollama_state.setStyleSheet(f"color:{color}; font-size:12px;")
        if pulse:
            eff = QGraphicsOpacityEffect(self.lbl_ollama_state)
            self.lbl_ollama_state.setGraphicsEffect(eff)
            anim = QPropertyAnimation(eff, b"opacity", self)
            anim.setDuration(1600)
            anim.setStartValue(0.45)
            anim.setEndValue(1.0)
            anim.setLoopCount(-1)
            anim.setEasingCurve(QEasingCurve.Type.InOutSine)
            anim.start()
            self._breath = anim

    # ---- 云端模型检测 ----
    def on_detect_models(self):
        base = self.edit_base.text().strip()
        key = self.edit_key.text().strip()
        if not base:
            QMessageBox.warning(self, "提示", "先填 API 地址")
            return
        self.btn_detect.setEnabled(False)
        self.lbl_detect_state.setText("检测中…")
        threading.Thread(target=self._detect_cloud_models, args=(base, key), daemon=True).start()

    def _detect_cloud_models(self, base, key):
        try:
            import requests
            headers = {"Authorization": f"Bearer {key}"} if key else {}
            r = requests.get(f"{base.rstrip('/')}/models", headers=headers, timeout=15)
            if r.status_code == 200:
                data = r.json().get("data", [])
                models = [m.get("id") for m in data if m.get("id")]
                self.cloud_models_detected.emit(True, models, "")
            else:
                self.cloud_models_detected.emit(False, [], f"HTTP {r.status_code}")
        except Exception as e:
            self.cloud_models_detected.emit(False, [], str(e)[:120])

    def _on_cloud_models_detected(self, ok, models, err):
        self.btn_detect.setEnabled(True)
        if ok and models:
            self.edit_model.clear()
            self.edit_model.addItems(models)
            self.lbl_detect_state.setText(f"找到 {len(models)} 个模型，选一个即可")
            self.lbl_detect_state.setStyleSheet("color:#4A6B4A; font-size:11px;")
        elif ok:
            self.lbl_detect_state.setText("服务通了，但没返回模型列表")
            self.lbl_detect_state.setStyleSheet("color:#7A7366; font-size:11px;")
        else:
            self.lbl_detect_state.setText(f"没连上：{err}")
            self.lbl_detect_state.setStyleSheet("color:#8B2C1F; font-size:11px;")

    # ---- 文稿 ----
    def on_browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选个地方存课堂记录", self.edit_dir.text() or PROJECT_DIR)
        if d:
            self.edit_dir.setText(d)
            self._update_transcript_preview()

    def _update_transcript_preview(self):
        tdir = self.edit_dir.text().strip() or "文稿"
        if not self.chk_transcript.isChecked():
            self.edit_dir.setPlaceholderText("这次不记笔记")
            self.edit_dir.setEnabled(False)
            self.btn_browse.setEnabled(False)
            return
        self.edit_dir.setEnabled(True)
        self.btn_browse.setEnabled(True)
        self.edit_dir.setPlaceholderText("将存到: " + tdir + "\\课堂记录_日期时间.md")

    # ---- 启动 ----
    def on_start(self):
        if _instance_running():
            QMessageBox.information(
                self, "已在运行",
                "俄汉同传已经在跑了（看右下角托盘图标）。\n\n"
                "找不到字幕窗就右键托盘选「显示字幕」；想彻底关掉选「退出全部」。"
            )
            return
        cfg = load_config()
        t = cfg.setdefault("translate", {})
        t["refine"] = self.chk_refine.isChecked()
        if self.btn_nllb.isChecked():
            # 本地 NLLB：毫秒级草稿 +（开关）云端修正
            t["backend"] = "hybrid"
            t["local_model"] = "models/nllb-200-distilled-600M"
        elif self.btn_fast.isChecked():
            # 极速模式：专用翻译 API
            provider = self.combo_fast_provider.currentData() or "mymemory"
            t["backend"] = "fast"
            t["fast"] = {
                "provider": provider,
                "appid": self.edit_baidu_appid.text().strip(),
                "secret": self.edit_baidu_secret.text().strip(),
            }
        elif self.btn_local.isChecked():
            t["backend"] = "cloud"
            model = self.combo_model.currentText().strip()
            if not model:
                QMessageBox.warning(self, "提示", "选个模型再开始")
                return
            t["cloud"] = {"provider": "ollama", "base_url": "http://localhost:11434",
                          "api_key": "", "model": model}
        else:
            t["backend"] = "cloud"
            base = self.edit_base.text().strip()
            key = self.edit_key.text().strip()
            model = self.edit_model.currentText().strip()
            if not base or not model:
                QMessageBox.warning(self, "提示", "云端模式要填 API 地址和模型名")
                return
            t["cloud"] = {"provider": "openai_compatible", "base_url": base,
                          "api_key": key, "model": model}
        cfg["save_transcript"] = self.chk_transcript.isChecked()
        cfg["transcript_dir"] = self.edit_dir.text().strip() or "文稿"
        ui = cfg.setdefault("ui", {})
        ui["font_size"] = self.slider_font.value()
        ui["font_size_zh"] = self.slider_font.value()  # 中俄同号对齐
        ui["opacity"] = self.slider_opacity.value() / 100.0
        save_config(cfg)
        self.lbl_status.setText("●  启动中…")
        self.lbl_status.setStyleSheet("color:#33536B;")
        try:
            if getattr(sys, "frozen", False):
                # 打包环境：同一 exe 以 --run 模式启动字幕
                subprocess.Popen([sys.executable, "--run"], cwd=PROJECT_DIR)
            else:
                subprocess.Popen([VENV_PYTHONW, os.path.join(PROJECT_DIR, "main.py"), "--run"],
                                 cwd=PROJECT_DIR)
            self.lbl_status.setText("●  已启动，字幕窗马上出现")
            self.lbl_status.setStyleSheet("color:#4A6B4A;")
        except Exception as e:
            self.lbl_status.setText("启动失败")
            self.lbl_status.setStyleSheet("color:#8B2C1F;")
            QMessageBox.critical(self, "启动失败", str(e))


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(PAPER_QSS)
    w = Launcher()
    # 高度自适应内容，避免布局被压扁
    h = w.layout().sizeHint().height()
    w.resize(540, min(max(h + 24, 520), 900))
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
