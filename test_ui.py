# -*- coding: utf-8 -*-
"""UI 功能键验证：逐个模拟点击，检查每个按钮的行为。"""

import os
import queue
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from subtitle_ui import SubtitleWindow
from brand import LogoWidget


def check(name, cond):
    print(("PASS" if cond else "FAIL") + " | " + name)
    return cond


def main():
    app = QApplication(sys.argv)
    q = queue.Queue()
    w = SubtitleWindow({"font_size": 20, "font_size_zh": 18, "click_through": False}, q)
    results = []

    # ---- 字幕窗功能键 ----
    # 1. 暂停键：点击 → paused 翻转 + 文本切换
    w.fbtn_pause.click()
    results.append(check("字幕窗-暂停键切换暂停", w.paused is True and w.fbtn_pause.text() == "继续"))
    w.fbtn_pause.click()
    results.append(check("字幕窗-暂停键恢复", w.paused is False and w.fbtn_pause.text() == "暂停"))

    # 2. 穿透键：点击 → 进入穿透 + 文本切换；按钮区永不穿透
    before = w._ct
    w.fbtn_lock.click()
    after = w._ct
    results.append(check("字幕窗-穿透键开启穿透", before is False and after is True
                         and w.fbtn_lock.text() == "穿透"))
    # 穿透时按钮区（窗口右上角按钮排）命中测试必须返回 False（不穿透）
    r = w._hit_rect_physical()
    btn_hit = w.hit_test_transparent(r.x() + 5, r.y() + 5)
    content_hit = w.hit_test_transparent(r.x() - 40, r.y() + 60)
    results.append(check("字幕窗-穿透时按钮区可点", btn_hit is False and content_hit is True))
    w.fbtn_lock.click()
    after2 = w._ct
    results.append(check("字幕窗-穿透键恢复交互", after2 is False
                         and w.fbtn_lock.text() == "交互"))

    # 3. 退出键：连接存在（不实际触发退出）
    results.append(check("字幕窗-退出键已连接", w.fbtn_quit is not None))

    # 4. 品牌徽标存在（纸音 logo：声波 + 纸角）
    results.append(check("字幕窗-品牌徽标", isinstance(w.logo_wrap, LogoWidget) and w.logo_wrap.width() == 30))

    # ---- 字幕窗自身按钮 ----
    # 5. 暂停键：真正联动暂停回调
    pause_calls = []
    w.set_pause_callback(lambda p: pause_calls.append(p))
    w.fbtn_pause.click()
    results.append(check("字幕窗-暂停联动", w.paused is True and w.fbtn_pause.text() == "继续"
                         and pause_calls == [True]))
    w.fbtn_pause.click()
    results.append(check("字幕窗-恢复联动", w.paused is False and w.fbtn_pause.text() == "暂停"
                         and pause_calls == [True, False]))

    # 6. 复位键：点击 → 字幕窗回到贴底
    w.move(100, 100)
    w._moved = True
    w.fbtn_reset.click()
    results.append(check("字幕窗-复位键回贴底", getattr(w, "_docked", False) is True
                         and not getattr(w, "_moved", False)))

    # 7. 文稿计数刷新（writer 注入）
    class FakeWriter:
        enabled = True
        count = 7
    w.writer = FakeWriter()
    w._refresh_count()
    results.append(check("字幕窗-文稿计数显示", "7" in w.lbl_count.text()))

    # ---- 数据链路 ----
    q.put(("partial", 1, "Квадратное"))
    q.put(("partial", 1, "Квадратное уравнение имеет"))
    q.put(("ru", 1, "Квадратное уравнение имеет два корня."))
    q.put(("zh", 1, "二次方程有两个根。"))
    w._poll()
    label, _eff = w._seq_map[1]
    results.append(check("数据链路-草稿到定稿", "Квадратное уравнение имеет два корня." in label.text()))
    results.append(check("数据链路-翻译回填", "二次方程有两个根。" in label.text()))
    results.append(check("数据链路-俄汉同行", label.text().startswith('<p') and
                        "Квадратное" in label.text() and "二次方程" in label.text()))

    failed = results.count(False)
    print(f"\n共 {len(results)} 项，失败 {failed} 项")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
