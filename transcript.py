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
        self._file = None
        if not enabled:
            return
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        d = os.path.join(base_dir, transcript_dir)
        try:
            os.makedirs(d, exist_ok=True)
            self.path = os.path.join(d, f"课堂记录_{ts}.md")
            self._file = open(self.path, "w", encoding="utf-8", buffering=1)
            self._file.write("# 俄汉课堂记录\n\n")
            self._file.write("生成时间：%s\n\n---\n\n" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
        except Exception as e:
            print(f"[文稿] 初始化失败: {e}")
            self.enabled = False

    def append(self, ru: str, zh: str):
        if not self.enabled or not self.path:
            return
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        with self._lock:
            try:
                if self._file is None:
                    self._file = open(self.path, "a", encoding="utf-8", buffering=1)
                self._file.write(f"## {ts}\n\n**俄语**：{ru}\n\n**中文**：{zh}\n\n")
                self._file.flush()
                self.count += 1
            except Exception as e:
                print(f"[文稿] 写入失败: {e}")

    def close(self):
        """关闭文稿文件句柄（进程退出时调用）。"""
        with self._lock:
            if self._file is not None:
                try:
                    self._file.close()
                except Exception:
                    pass
                self._file = None
