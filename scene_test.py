# -*- coding: utf-8 -*-
"""两个关键场景识别测试：日常对话（慢）+ 快速口语（+40%），独立容错。"""

import asyncio
import av
import edge_tts
import numpy as np
import os
import subprocess
import time
import wave
import winsound

proj = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(proj, ".venv", "Scripts", "python.exe")
PYW = os.path.join(proj, ".venv", "Scripts", "pythonw.exe")


def stop_all():
    subprocess.run([PY, os.path.join(proj, "main.py"), "--stop"],
                   capture_output=True, timeout=10)


def build_wav(sentences, rate, out):
    async def gen(text, idx):
        c = edge_tts.Communicate(text, "ru-RU-DmitryNeural", rate=rate)
        await c.save(f"seg_{idx}.mp3")

    async def main():
        for i, s in enumerate(sentences):
            await gen(s, i)

    asyncio.run(main())
    chunks = []
    for i in range(len(sentences)):
        inp = av.open(f"seg_{i}.mp3")
        stream = next(s for s in inp.streams if s.type == "audio")
        frames = [f.to_ndarray() for f in inp.decode(stream)]
        audio = np.concatenate(frames, axis=1).mean(axis=0).astype(np.float32)
        src = stream.rate or 24000
        n = int(len(audio) * 16000 / src)
        idx = np.linspace(0, len(audio) - 1, n)
        chunks.append(np.interp(idx, np.arange(len(audio)), audio).astype(np.float32))
        if i < len(sentences) - 1:
            chunks.append(np.zeros(19200, dtype=np.float32))
    full = np.concatenate(chunks)
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes((np.clip(full, -1, 1) * 32767).astype(np.int16).tobytes())
    for i in range(len(sentences)):
        try:
            os.remove(f"seg_{i}.mp3")
        except OSError:
            pass
    return len(full) / 16000


def run_scene(name, sentences, rate):
    print(f"\n===== {name} (rate {rate}) =====")
    stop_all()
    wav = os.path.join(proj, "scene_tmp.wav")
    dur = build_wav(sentences, rate, wav)
    log = os.path.join(proj, "log.txt")
    if os.path.exists(log):
        os.remove(log)

    p = subprocess.Popen([PYW, os.path.join(proj, "main.py"), "--run"], cwd=proj)
    time.sleep(25)  # 模型加载
    winsound.PlaySound(wav, winsound.SND_FILENAME)
    time.sleep(dur + 18)

    # 先读 log（此时 --run 实例还在，log 是它的），再 stop
    recs, trans = [], []
    if os.path.exists(log):
        with open(log, encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "[识别]" in line and "加载" not in line and "完成" not in line:
                    recs.append(line.split("]", 1)[1].strip())
                elif "[翻译]" in line and all(k not in line for k in
                        ("使用", "警告", "跳过", "失败")):
                    trans.append(line.split("]", 1)[1].strip())
    stop_all()
    ok = sum(1 for t in trans if "缺失" not in t)
    print(f"识别: {len(recs)}/{len(sentences)} 句")
    for r in recs:
        print("  ", r[:75])
    print(f"翻译成功: {ok}/{len(trans)}")
    for t in trans:
        print("  ", t[:60])
    os.remove(wav)


if __name__ == "__main__":
    run_scene("日常对话", [
        "Привет, как дела? Я сегодня очень занят.",
        "Давай встретимся завтра в кафе.",
        "Мне нужно купить хлеб и молоко.",
    ], "+0%")
    time.sleep(2)
    run_scene("快速口语", [
        "Слушай, мы же договаривались на пятницу, а ты опять всё переносишь!",
        "Я тебе сто раз говорил, проверяй почту перед отправкой!",
        "Ладно ладно, давай быстро решим этот вопрос и пошли обедать.",
    ], "+40%")
    time.sleep(2)
    run_scene("新闻播报", [
        "Сегодня в Москве ожидается переменная облачность, без осадков.",
        "Президент подписал новый закон о цифровой экономике.",
        "На фондовом рынке наблюдается небольшой рост основных индексов.",
    ], "+10%")
    time.sleep(2)
    run_scene("课程讲解", [
        "Закон Ома гласит, что сила тока прямо пропорциональна напряжению.",
        "При последовательном соединении сопротивления складываются.",
        "Напряжение на участке цепи измеряется в вольтах.",
    ], "+5%")
