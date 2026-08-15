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
        self.on_error = None  # 可选回调：连续重连失败时通知 UI

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="audio-capture")
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        """采集主循环：带异常保护与自动重连，设备丢失不静默死亡。"""
        consecutive_failures = 0
        while not self._stop.is_set():
            try:
                device = pick_loopback_device(self.device_hint)
                if device is None:
                    raise RuntimeError("未找到可用的回环音频设备")
                consecutive_failures = 0
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
            except Exception as e:
                consecutive_failures += 1
                print(f"[采集] 设备异常（{e}），1 秒后重连…")
                if consecutive_failures >= 3 and self.on_error:
                    try:
                        self.on_error(f"音频设备丢失或不可用（{e}），正在重连…")
                    except Exception:
                        pass
                # 停止事件可能已在重试间隙被设置，检查后决定是否继续等待
                if not self._stop.is_set():
                    import time
                    time.sleep(1)
