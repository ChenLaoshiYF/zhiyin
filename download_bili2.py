# -*- coding: utf-8 -*-
"""从 B站搜索多个题材的真实俄语人声视频，下载音频流（m4s），用 PyAV 解码成 wav。
题材：天气预报、访谈、纪录片旁白、新闻、教学，扩充真实人声测试库。
"""
import json
import os
import re
import time

import requests
import av
import numpy as np
import wave

PROJECT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(PROJECT, "test_audio", "real")
os.makedirs(OUT_DIR, exist_ok=True)

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
}

sess = requests.Session()
sess.headers.update(H)
try:
    sess.get("https://www.bilibili.com/", timeout=15)  # 拿 buvid3 cookie，绕过 412
except Exception:
    pass


def search(keyword, count=6):
    url = "https://api.bilibili.com/x/web-interface/search/type"
    params = {"search_type": "video", "keyword": keyword, "page": 1, "page_size": count}
    d = sess.get(url, params=params, timeout=15).json()
    out = []
    for item in d.get("data", {}).get("result", []):
        out.append({
            "title": re.sub(r"<[^>]+>", "", item.get("title", "")),
            "bvid": item.get("bvid"),
            "duration": item.get("duration", ""),
        })
    return out


def get_audio(bvid):
    page = sess.get(
        f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}", timeout=15).json()
    cid = page["data"]["cid"]
    play = sess.get(
        f"https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&fnval=16",
        timeout=15).json()
    dash = play.get("data", {}).get("dash") or {}
    audios = dash.get("audio") or []
    if not audios:
        return None
    audios.sort(key=lambda a: a.get("bandwidth", 0))
    return audios[-1]["baseUrl"]


def m4s_to_wav(m4s_path, wav_path, seconds=60, skip=3.0):
    """PyAV 解码 m4s → 16k 单声道 wav，跳过片头。"""
    inp = av.open(m4s_path)
    try:
        stream = next(s for s in inp.streams if s.type == "audio")
        src = stream.rate or 48000
        skip_n = int(skip * src)
        max_n = int((skip + seconds) * src)
        frames = []
        total = 0
        for f in inp.decode(stream):
            total += f.samples
            if total <= skip_n:
                continue
            frames.append(f.to_ndarray())
            if total >= max_n:
                break
    finally:
        inp.close()
    if not frames:
        return None
    audio = np.concatenate(frames, axis=1).mean(axis=0).astype(np.float32)
    n = int(len(audio) * 16000 / src)
    xi = np.linspace(0, len(audio) - 1, max(n, 1))
    audio16 = np.interp(xi, np.arange(len(audio)), audio).astype(np.float32)
    with wave.open(wav_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes((np.clip(audio16, -1, 1) * 32767).astype(np.int16).tobytes())
    return wav_path


def main():
    topics = [
        ("访谈", "интервью"),
        ("纪录片", "СССР документальный"),
        ("教学", "русский язык урок"),
        ("文化", "Москва история"),
        ("演讲", "выступление речь"),
        ("播报", "прогноз погоды Россия"),
    ]
    seen = set()
    idx = 10
    manifest = []
    for tag, topic in topics:
        print(f"== 搜索: {topic}")
        try:
            items = search(topic, count=6)
        except Exception as e:
            print(f"   搜索失败: {e}")
            time.sleep(3)
            continue
        for it in items:
            if it["bvid"] in seen or len(it["title"]) < 8:
                continue
            if "4K" in it["title"] or "音乐" in it["title"] or "music" in it["title"].lower():
                continue
            if not re.search(r"[а-яА-ЯёЁ]", it["title"]):
                continue  # 标题不含西里尔字母，多半不是俄语内容
            seen.add(it["bvid"])
            try:
                url = get_audio(it["bvid"])
                if not url:
                    continue
                m4s = os.path.join(OUT_DIR, f"tmp_{idx}.m4s")
                if os.path.exists(m4s):
                    os.remove(m4s)
                with sess.get(url, timeout=90, stream=True) as r, open(m4s, "wb") as f:
                    for chunk in r.iter_content(65536):
                        f.write(chunk)
                wav = os.path.join(OUT_DIR, f"real_{idx}.wav")
                m4s_to_wav(m4s, wav, seconds=60)
                os.remove(m4s)
                size = os.path.getsize(wav) / 1024
                manifest.append({"idx": idx, "tag": tag, "title": it["title"][:60], "kb": round(size)})
                print(f"   real_{idx}.wav  {size:.0f}KB  [{tag}] {it['title'][:45]}")
                idx += 1
                if idx >= 16:
                    break
            except Exception as e:
                print(f"   失败 {it['bvid']}: {str(e)[:60]}")
                continue
            time.sleep(2)
        if idx >= 16:
            break
    with open(os.path.join(OUT_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print("完成:", len(manifest), "段")


if __name__ == "__main__":
    main()
