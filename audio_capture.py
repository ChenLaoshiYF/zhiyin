"""系统音频采集：WASAPI Loopback -> 16kHz 单声道 -> 队列

不依赖虚拟声卡，直接抓系统输出，兼容所有网课平台。
"""

import queue
import threading

import numpy as np
import soundcard as sc


def _resample_to_16k(x: np.ndarray, src_rate: int) -> np.ndarray:
    """线性插值重采样到 16kHz（对 ASR 足够，避免引入 scipy 依赖）。"""
    if src_rate == 16000:
        return x.astype(np.float32)
    n_out = int(len(x) * 16000 / src_rate)
    idx = np.linspace(0, len(x) - 1, n_out)
    return np.interp(idx, np.arange(len(x)), x).astype(np.float32)


def pick_loopback_device(name_hint: str = "auto"):
    """选择回环设备：优先默认扬声器对应的回环，避免抓到虚拟设备。"""
    mics = sc.all_microphones(include_loopback=True)
    loopbacks = [m for m in mics if "麦克风" not in m.name and "Microphone" not in m.name]
    if name_hint and name_hint != "auto":
        for m in loopbacks:
            if name_hint.lower() in m.name.lower():
                return m
    try:
        default = sc.default_speaker().name
        for m in loopbacks:
            if m.name.strip().lower() == default.strip().lower():
                return m
    except Exception:
        pass
    return loopbacks[0] if loopbacks else (mics[0] if mics else None)


class AudioCapture:
    """后台线程：循环抓取系统输出音频，切成 16k mono 小块放入队列。"""

    def __init__(self, chunk_sec=0.1, device_hint="auto", sample_rate=16000):
        self.chunk_sec = chunk_sec
        self.device_hint = device_hint
        self.sample_rate = sample_rate
        self.audio_q = queue.Queue(maxsize=512)
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="audio-capture")
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        device = pick_loopback_device(self.device_hint)
        if device is None:
            print("[采集] 未找到可用的回环音频设备")
            return
        print(f"[采集] 正在抓取系统音频: {device.name}")
        with device.recorder(samplerate=48000, channels=2, blocksize=4800) as rec:
            while not self._stop.is_set():
                data = rec.record(numframes=int(48000 * self.chunk_sec))
                if data is None or len(data) == 0:
                    continue
                mono = data.mean(axis=1)
                mono_16k = _resample_to_16k(mono, 48000)
                try:
                    self.audio_q.put(mono_16k, timeout=0.5)
                except queue.Full:
                    pass
