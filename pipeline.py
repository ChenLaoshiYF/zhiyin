# -*- coding: utf-8 -*-
"""流水线编排：采集 → 识别 → 翻译（并行流式）→ UI 队列

模块职责分离：本模块只做编排，各环节逻辑在 audio_capture / asr_engine /
translator 中。UI 线程只消费 ui_q，不做任何推理。

并行翻译：句子带序号（seq）派发给线程池，完成时按序号回填，
保证"俄文逐句滚动、中文异步补齐"且不乱序。任何一句卡住都不阻塞后续。
"""

import itertools
import os
import queue
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from audio_capture import AudioCapture
from asr_engine import ASREngine
from translator import TranslatorManager
from transcript import TranscriptWriter

# 消息协议（ui_q）：
#   ("partial", seq, text)   草稿（说话中，随说话更新，可能多次）
#   ("ru", seq, text)        定稿（草稿的最终版）
#   ("zh", seq, partial)     定稿句的中文翻译增量


class Pipeline:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.ui_q = queue.Queue(maxsize=256)
        self._audio_q = queue.Queue(maxsize=512)
        self._stop = threading.Event()
        self._paused = False
        self._seq = itertools.count(1)
        # 翻译上下文排序缓冲：并发 worker 完成后按 seq 顺序交给 translator
        self._ctx_lock = threading.Lock()
        self._ctx_pending = {}
        self._ctx_next = 1
        self._ctx_max_gap = 64  # 跳号超过此值则强制清空（防泄漏）

        # 打包后 __file__ 指向临时解压目录，必须用 exe 所在目录做基准，
        # 否则课堂记录写进临时目录，退出即消失
        base_dir = (os.path.dirname(os.path.abspath(sys.executable))
                    if getattr(sys, "frozen", False)
                    else os.path.dirname(os.path.abspath(__file__)))
        self._base_dir = base_dir
        # 模型相对路径转绝对：快捷方式/异目录启动时 cwd 不可靠（必须在使用前完成）
        asr_model = cfg["asr"].get("model", "large-v3-turbo")
        if not os.path.isabs(asr_model):
            asr_model = os.path.join(base_dir, asr_model)
        t_cfg = cfg.setdefault("translate", {})
        local_model = t_cfg.get("local_model", "models/nllb-200-distilled-600M")
        if not os.path.isabs(local_model):
            t_cfg["local_model"] = os.path.join(base_dir, local_model)

        cap = AudioCapture(
            chunk_sec=cfg["audio"].get("chunk_sec", 0.1),
            device_hint=cfg["audio"].get("loopback_device", "auto"),
        )
        cap.audio_q = self._audio_q
        self.cap = cap

        self.asr = ASREngine(
            model=asr_model,
            device=cfg["asr"].get("device", "auto"),
            compute_type=cfg["asr"].get("compute_type", "float16"),
            language=cfg["asr"].get("language", "ru"),
            beam_size=cfg["asr"].get("beam_size", 1),
            model_dir=cfg["asr"].get("model_dir", "models"),
            min_speech_sec=cfg["asr"].get("min_speech_sec", 1.5),
            silence_sec=cfg["asr"].get("silence_sec", 0.8),
        )
        self.asr.bind_audio_queue(self._audio_q)

        self.translator = TranslatorManager(cfg)
        self.writer = TranscriptWriter(
            cfg.get("save_transcript", True),
            base_dir,
            cfg.get("transcript_dir", "文稿"),
        )

    def start(self):
        self.asr.load()
        self.cap.start()
        self.asr.start()
        # 并行翻译：DeepSeek 单句约 2s，3 路并行吞吐翻三倍；seq 配对不乱序
        workers = int(self.cfg.get("translate_workers", 3))
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="translate")
        t = threading.Thread(target=self._translation_loop, daemon=True, name="translator")
        t.start()

    def set_paused(self, paused: bool):
        """暂停/恢复整条链路：识别缓冲丢弃，翻译循环停消费；恢复后重新开始。"""
        self._paused = paused
        self.asr.set_paused(paused)
        if paused:
            # 丢弃已排队的翻译任务（pending 的 final）
            while True:
                try:
                    self.asr.result_q.get_nowait()
                except queue.Empty:
                    break

    def stop(self):
        self._stop.set()
        self.cap.stop()
        # 停止后立即取消未开始的翻译任务；正在执行的等它跑完（或随进程退出）
        executor = getattr(self, "_executor", None)
        if executor is not None:
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except Exception as e:
                print(f"[流水线] 关闭翻译线程池异常: {e}")

    def _commit_context(self, seq: int, zh: str):
        """按 seq 顺序提交翻译上下文（并发安全，容忍跳号）。"""
        with self._ctx_lock:
            self._ctx_pending[seq] = zh
            # 顺序提交连续 seq
            while self._ctx_next in self._ctx_pending:
                z = self._ctx_pending.pop(self._ctx_next)
                self.translator.add_context(z)
                self._ctx_next += 1
            # 跳号保护：pending 中最早的 seq 落后当前太多，说明中间 seq 被跳过/丢弃
            if self._ctx_pending:
                oldest = min(self._ctx_pending)
                if oldest - self._ctx_next > self._ctx_max_gap:
                    # 强制按序提交剩余（放弃严格顺序，避免上下文永久挂起）
                    for s in sorted(self._ctx_pending):
                        self.translator.add_context(self._ctx_pending.pop(s))
                    self._ctx_next = max(self._ctx_next, (oldest + 1) if self._ctx_pending else seq + 1)

    def _translation_loop(self):
        """消费 ASR 结果：草稿实时上屏，定稿后提交翻译（并行）。"""
        current_seq = None
        while not self._stop.is_set():
            if self._paused:
                current_seq = None  # 丢弃挂起的草稿态
                time.sleep(0.2)
                continue
            msg = self.asr.consume(timeout=0.2)
            if msg is None:
                continue
            kind, text = msg
            if kind == "partial":
                if current_seq is None:
                    current_seq = next(self._seq)
                try:
                    self.ui_q.put(("partial", current_seq, text), timeout=0.5)
                except queue.Full:
                    pass
            else:  # final 定稿
                if current_seq is None:
                    current_seq = next(self._seq)
                try:
                    self.ui_q.put(("ru", current_seq, text), timeout=0.5)
                except queue.Full:
                    pass
                try:
                    self._executor.submit(self._translate_and_push, current_seq, text)
                except Exception as e:
                    print(f"[翻译] 提交失败: {e}")
                current_seq = None

    def _translate_and_push(self, seq: int, ru_text: str):
        """翻译（线程池执行），流式增量按 seq 回填，完成后收尾。"""
        backend = self.translator.backend

        if backend in ("local", "hybrid"):
            # 混合：本地草稿毫秒级出 → 云端修正替换
            def push(acc: str):
                try:
                    self.ui_q.put(("zh", seq, acc), timeout=0.5)
                except queue.Full:
                    pass

            try:
                zh_text = self.translator.translate_hybrid(ru_text, on_draft=push, on_final=push)
            except Exception as e:
                print(f"[翻译] 混合翻译失败: {e}")
                zh_text = f"[翻译失败] {ru_text}"
        else:
            def on_token(acc: str):
                try:
                    self.ui_q.put(("zh", seq, acc), timeout=0.5)
                except queue.Full:
                    pass

            try:
                zh_text = self.translator.translate_stream(ru_text, on_token)
            except Exception as e:
                print(f"[翻译] 失败: {e}")
                zh_text = f"[翻译失败] {ru_text}"
        try:
            self.ui_q.put(("zh", seq, zh_text), timeout=0.5)
        except queue.Full:
            pass
        # 翻译缺失/失败的句子不进文稿，也不污染后续翻译上下文
        if zh_text.startswith("[译文缺失]") or zh_text.startswith("[翻译失败]"):
            print(f"[文稿] 跳过缺失翻译: {ru_text}")
            return
        # 上下文入队（按 seq 排序，容忍跳号，见 _commit_context）
        try:
            self._commit_context(seq, zh_text)
        except Exception as e:
            print(f"[翻译] 更新上下文失败: {e}")
        try:
            self.writer.append(ru_text, zh_text)
        except Exception as e:
            print(f"[文稿] 写入失败: {e}")
        print(f"[{time.strftime('%H:%M:%S')}] [翻译] {zh_text}")
