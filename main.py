# -*- coding: utf-8 -*-
"""俄汉同传 · 主入口

采集系统音频 → 俄语识别 → 流式翻译 → 悬浮字幕
由 launcher.pyw 启动（pythonw 无控制台）；日志写入 log.txt

关闭方式（三选一）：
  1. 控制条「退出」按钮
  2. 关闭字幕窗（Alt+F4）
  3. 系统托盘图标右键「退出全部」

命令行兜底：python main.py --stop   强制关闭运行中的实例
"""

import json
import os
import subprocess
import sys

from brand import APP_TITLE

# Windows 环境三件套（WhisperLive 经验）：避免 OpenMP 运行时冲突
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "8")

PROJECT_DIR = (os.path.dirname(os.path.abspath(sys.executable))
               if getattr(sys, "frozen", False)
               else os.path.dirname(os.path.abspath(__file__)))
LOCK_PATH = os.path.join(PROJECT_DIR, "app.lock")

# 无控制台运行（pythonw）：所有输出写日志文件，方便排查
_LOG_PATH = os.path.join(PROJECT_DIR, "log.txt")
_logf = open(_LOG_PATH, "w", encoding="utf-8", buffering=1)  # 行缓冲，即时落盘
sys.stdout = _logf
sys.stderr = _logf


def _pid_alive(pid: int) -> bool:
    """检查 PID 是否存活（不要求权限）。"""
    import ctypes
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if h:
        ctypes.windll.kernel32.CloseHandle(h)
        return True
    return False


def _handle_stop():
    """--stop：按锁文件中的 PID 强制结束旧实例。"""
    if not os.path.exists(LOCK_PATH):
        print("没有正在运行的实例")
        sys.exit(0)
    try:
        with open(LOCK_PATH, "r") as f:
            pid = int(f.read().strip())
    except Exception:
        print("锁文件损坏，清理后退出")
        os.remove(LOCK_PATH)
        sys.exit(0)
    if _pid_alive(pid):
        subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                       capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        print(f"已关闭同传进程 {pid}")
    else:
        print(f"进程 {pid} 已不在运行，清理锁文件")
    try:
        os.remove(LOCK_PATH)
    except OSError:
        pass
    sys.exit(0)


def _check_single_instance() -> bool:
    """已有存活实例时返回 True，阻止重复启动。"""
    if os.path.exists(LOCK_PATH):
        try:
            with open(LOCK_PATH, "r") as f:
                pid = int(f.read().strip())
        except Exception:
            pid = -1
        if pid > 0 and _pid_alive(pid):
            print(f"已有实例在运行 (PID {pid})，本次启动取消。"
                  f"如需强制关闭：main.py --stop")
            return True
    return False


def _write_lock():
    with open(LOCK_PATH, "w") as f:
        f.write(str(os.getpid()))


def _remove_lock():
    try:
        os.remove(LOCK_PATH)
    except OSError:
        pass


def _make_tray_icon():
    """纸音品牌徽标作为托盘图标。"""
    from PyQt6.QtGui import QIcon
    from brand import LogoWidget
    return QIcon(LogoWidget(64).grab())


def setup_tray(app, win):
    """系统托盘：永远存在的「退出全部」入口。"""
    from PyQt6.QtGui import QAction
    from PyQt6.QtWidgets import QMenu, QSystemTrayIcon
    tray = QSystemTrayIcon(_make_tray_icon(), app)
    tray.setToolTip(APP_TITLE + " · 正在监听")
    menu = QMenu()
    act_toggle = QAction("显示 / 隐藏字幕", menu)
    act_toggle.triggered.connect(win.toggle_visible)
    act_quit = QAction("退出全部", menu)
    act_quit.triggered.connect(app.quit)
    menu.addAction(act_toggle)
    menu.addSeparator()
    menu.addAction(act_quit)
    tray.setContextMenu(menu)
    tray.show()
    return tray


def load_config():
    """加载 config.json，损坏/缺失时回退默认配置并提示（不崩溃）。"""
    path = os.path.join(PROJECT_DIR, "config.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[配置] config.json 读取失败（{e}），使用默认配置")
        return {}


def main():
    if "--stop" in sys.argv:
        _handle_stop()
    if "--run" in sys.argv:
        _run_subtitle()
    else:
        # 无参数：启动配置窗口（launcher 逻辑）
        from launcher import main as launcher_main
        launcher_main()


def _handle_stop_if_requested():
    if "--stop" in sys.argv:
        _handle_stop()


def _run_subtitle():
    if _check_single_instance():
        sys.exit(1)
    _write_lock()

    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.aboutToQuit.connect(_remove_lock)

    from pipeline import Pipeline

    cfg = load_config()
    pipe = Pipeline(cfg)
    pipe.start()

    from subtitle_ui import SubtitleWindow

    win = SubtitleWindow(cfg.get("ui", {}), pipe.ui_q, writer=pipe.writer)
    win.set_pause_callback(pipe.set_paused)

    # 全局热键 Ctrl+Shift+T：穿透/交互切换（穿透时按钮点不到，必须有键盘兜底）
    _hotkey_id = _install_hotkey(app, win)

    win.show()
    print("俄汉同传已启动。Ctrl+Shift+T 切换穿透。")

    try:
        setup_tray(app, win)
    except Exception as e:
        print(f"[托盘] 创建失败（不影响使用）: {e}")

    try:
        sys.exit(app.exec())
    except KeyboardInterrupt:
        pass
    finally:
        try:
            import ctypes
            ctypes.windll.user32.UnregisterHotKey(None, _hotkey_id)
        except Exception:
            pass
        pipe.stop()
        _remove_lock()


def _install_hotkey(app, win):
    """注册全局热键 Ctrl+Shift+T：切换字幕窗穿透/交互。返回 hotkey id。"""
    import ctypes
    import ctypes.wintypes
    from PyQt6.QtCore import QAbstractNativeEventFilter

    MOD_CONTROL = 0x0002
    MOD_SHIFT = 0x0004
    VK_T = 0x54
    WM_HOTKEY = 0x0312
    WM_NCHITTEST = 0x0084
    HTTRANSPARENT = -1
    HOTKEY_ID = 1

    def _toggle():
        win.set_click_through(not win._ct)

    class _Filter(QAbstractNativeEventFilter):
        def nativeEventFilter(self, eventType, message):
            if eventType == b"windows_generic_MSG":
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    _toggle()
                    return True, 0
                if msg.message == WM_NCHITTEST:
                    # 只处理字幕窗的消息：穿透模式下其他窗口（弹窗/对话框）必须保持可点
                    try:
                        if int(msg.hwnd) != int(win.winId()):
                            return False, 0
                    except Exception:
                        return False, 0
                    # 穿透模式：内容区逐点穿透（HTTRANSPARENT），按钮区保持可点
                    x = ctypes.c_short(msg.lParam & 0xFFFF).value
                    y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                    if win.hit_test_transparent(x, y):
                        return True, HTTRANSPARENT
            return False, 0

    try:
        ctypes.windll.user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL | MOD_SHIFT, VK_T)
        _f = _Filter()
        app.installNativeEventFilter(_f)
        print("[热键] Ctrl+Shift+T 切换穿透")
        return HOTKEY_ID
    except Exception as e:
        print(f"[热键] 注册失败: {e}")
        return None


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        crash = os.path.join(PROJECT_DIR, "crash.txt")
        try:
            with open(crash, "w", encoding="utf-8") as f:
                traceback.print_exc(file=f)
        except Exception:
            pass
        raise
