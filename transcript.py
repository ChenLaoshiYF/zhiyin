# -*- coding: utf-8 -*-
"""双语文稿保存：Markdown 格式，俄语原文 + 中文译文，带时间戳。"""

import datetime
import os
import threading


class TranscriptWriter:
    def __init__(self, enabled: bool, base_dir: str, transcript_dir: str = "文稿"):
        self.enabled = enabled
        self.count = 0
        self.path = None
        self._lock = threading.Lock()  # 多线程翻译并发写入，必须串行
        if not enabled:
            return
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        d = os.path.join(base_dir, transcript_dir)
        os.makedirs(d, exist_ok=True)
        self.path = os.path.join(d, f"课堂记录_{ts}.md")
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("# 俄汉课堂记录\n\n")
            f.write("生成时间：%s\n\n---\n\n" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))

    def append(self, ru: str, zh: str):
        if not self.enabled or not self.path:
            return
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(f"## {ts}\n\n**俄语**：{ru}\n\n**中文**：{zh}\n\n")
            self.count += 1
