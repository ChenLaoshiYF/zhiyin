# -*- coding: utf-8 -*-
"""俄语语音识别：faster-whisper + 静音切句 + 部分识别（草稿）

说话过程中周期性输出部分识别结果（草稿，随说话持续修正），
说完（静音）后输出最终定稿。消息格式：
    ("partial", text)  草稿（可能多次，同一句）
    ("final", text)    定稿（草稿的最终版，之后不会再变）

faster-whisper 基于 CTranslate2，不依赖 torch，float16 在 GPU 上很快。
"""

import queue
import threading
import time

import numpy as np

_HF_ENDPOINT = "https://hf-mirror.com"


class ASREngine:
    def __init__(self, model="large-v3-turbo", device="auto", compute_type="float16",
                 language="ru", beam_size=1, model_dir="models",
                 min_speech_sec=1.5, silence_sec=1.2, partial_interval=0.8):
        self.model_name = model
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.beam_size = beam_size
        self.model_dir = model_dir
        self.min_speech_sec = min_speech_sec
        self.silence_sec = silence_sec
        self.partial_interval = partial_interval  # 草稿更新间隔（秒）

        self.result_q = queue.Queue(maxsize=128)
        self._stop = threading.Event()
        self._paused = False
        self._thread = None
        self._model = None
        self._pending = ""       # 待合并的碎片（无句末标点的短句）
        self._pending_ts = 0.0

    def set_paused(self, paused: bool):
        """暂停/恢复：暂停时丢弃缓冲，恢复后从当下重新识别。"""
        self._paused = paused

    def load(self):
        import os
        os.environ.setdefault("HF_ENDPOINT", _HF_ENDPOINT)
        from faster_whisper import WhisperModel
        print(f"[识别] 加载模型 {self.model_name} ({self.device}/{self.compute_type}) ...")
        if os.path.isdir(self.model_name):
            self._model = WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type)
        else:
            self._model = WhisperModel(
                self.model_name, device=self.device, compute_type=self.compute_type,
                download_root=self.model_dir,
            )
        print("[识别] 模型加载完成")

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="asr")
        self._thread.start()

    def stop(self):
        self._stop.set()

    def bind_audio_queue(self, audio_q):
        self._audio_q = audio_q

    @staticmethod
    def _rms(x: np.ndarray) -> float:
        return float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0

    def _transcribe(self, audio: np.ndarray) -> str:
        """对一段音频转写，返回文本（空串表示无声/无效）。"""
        if self._model is None or len(audio) < 16000 * 0.4:
            return ""
        try:
            segments, _info = self._model.transcribe(
                audio, language=self.language, task="transcribe",
                beam_size=1, condition_on_previous_text=False,
                vad_filter=True, vad_parameters=dict(min_silence_duration_ms=200),
            )
            texts = [s.text.strip() for s in segments if s.text and s.text.strip()]
            return " ".join(texts).strip()
        except Exception as e:
            print(f"[识别] 转写失败: {e}")
            return ""

    def _run(self):
        buffer = np.zeros(0, dtype=np.float32)
        speech_sec = 0.0
        silence_sec = 0.0
        noise_floor = 1e-4
        last_partial_at = -1.0
        started_speech = False

        while not self._stop.is_set():
            if self._paused:
                # 暂停：丢弃积压与中间态，恢复后从当下重新开始
                while True:
                    try:
                        self._audio_q.get_nowait()
                    except queue.Empty:
                        break
                buffer = np.zeros(0, dtype=np.float32)
                speech_sec = 0.0
                silence_sec = 0.0
                last_partial_at = -1.0
                started_speech = False
                self._pending = ""
                time.sleep(0.2)
                continue
            # 碎片缓存超时：2.5 秒没有后续 → 单独推送，防止误并到下句
            if self._pending and time.time() - self._pending_ts > 2.5:
                self._emit_final(self._pending)
                self._pending = ""
            try:
                chunk = self._audio_q.get(timeout=0.2)
            except queue.Empty:
                continue

            rms = self._rms(chunk)
            if rms < 0.05:
                noise_floor = 0.9 * noise_floor + 0.1 * max(rms, 1e-5)

            chunk_sec = len(chunk) / 16000
            is_speech = rms > max(0.008, noise_floor * 8)

            if is_speech:
                buffer = np.concatenate([buffer, chunk])
                speech_sec += chunk_sec
                silence_sec = 0.0
                started_speech = True
                # 部分识别：说话过程中周期性出草稿
                if (speech_sec >= 0.6 and started_speech
                        and speech_sec - last_partial_at >= self.partial_interval):
                    text = self._transcribe(buffer)
                    if text:
                        print(f"[草稿] {text}")
                        try:
                            self.result_q.put(("partial", text), timeout=0.5)
                        except queue.Full:
                            pass
                    last_partial_at = speech_sec
            else:
                silence_sec += chunk_sec
                if silence_sec < 0.15 and started_speech:
                    buffer = np.concatenate([buffer, chunk])
                    speech_sec += chunk_sec
                elif speech_sec >= self.min_speech_sec and len(buffer) > 16000 * 0.4:
                    self._push_final(buffer)
                    buffer = np.zeros(0, dtype=np.float32)
                    speech_sec = 0.0
                    silence_sec = 0.0
                    last_partial_at = -1.0
                    started_speech = False
                else:
                    # 太短：如果有过草稿也收一个 final 保证闭合
                    if started_speech and len(buffer) > 16000 * 0.4:
                        self._push_final(buffer)
                    buffer = np.zeros(0, dtype=np.float32)
                    speech_sec = 0.0
                    silence_sec = 0.0
                    last_partial_at = -1.0
                    started_speech = False

            # 长句兜底：说太久强制切
            if speech_sec > 12.0:
                self._push_final(buffer)
                buffer = np.zeros(0, dtype=np.float32)
                speech_sec = 0.0
                silence_sec = 0.0
                last_partial_at = -1.0
                started_speech = False

    def _push_final(self, audio: np.ndarray):
        text = self._transcribe(audio)
        if not text:
            return
        text = text.strip()
        if len(text) < 6:
            return  # 尾音/杂音碎片（如 "без"、"и"），无信息量，直接丢弃
        # 碎片合并：短句一律先缓存（whisper 每段都带句号，不能靠标点判断），
        # 凑够 30 字符或超时再推，避免一句话被切成多段记录/显示
        merged = (self._pending + " " + text).strip() if self._pending else text
        if len(merged) < 30:
            self._pending = merged
            self._pending_ts = time.time()
        else:
            self._pending = ""
            self._emit_final(merged)

    def _emit_final(self, text: str):
        if not text:
            return
        try:
            self.result_q.put(("final", text), timeout=0.5)
        except queue.Full:
            pass
        print(f"[{time.strftime('%H:%M:%S')}] [识别] {text}")

    def consume(self, timeout=0.1):
        """返回 ("partial"|"final", text)，无消息返回 None。"""
        try:
            return self.result_q.get(timeout=timeout)
        except queue.Empty:
            return None
