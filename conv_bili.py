# -*- coding: utf-8 -*-
"""B站 m4s → wav 转换（真实人声测试用）"""

import glob
import json
import os

import av
import numpy as np
import wave

dest = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_audio", "real")

for m4s in sorted(glob.glob(os.path.join(dest, "bili_*.m4s"))):
    idx = os.path.basename(m4s).split("_")[1].split(".")[0]
    out = os.path.join(dest, f"real_{idx}.wav")
    if os.path.exists(out):
        continue
    inp = av.open(m4s)
    stream = next(s for s in inp.streams if s.type == "audio")
    frames = []
    total = 0
    for f in inp.decode(stream):
        frames.append(f.to_ndarray())
        total += f.samples
        if total > 960000:  # 前 60 秒
            break
    audio = np.concatenate(frames, axis=1).mean(axis=0).astype(np.float32) if frames else np.zeros(0)
    src = stream.rate or 48000
    n = int(len(audio) * 16000 / src)
    xi = np.linspace(0, len(audio) - 1, n)
    audio16 = np.interp(xi, np.arange(len(audio)), audio).astype(np.float32)
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes((np.clip(audio16, -1, 1) * 32767).astype(np.int16).tobytes())
    meta = json.load(open(m4s.replace(".m4s", ".json"), encoding="utf-8"))
    print(f"real_{idx}: {len(audio16)/16000:.0f}s | {meta['title'][:40]}")
