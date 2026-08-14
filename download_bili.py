# -*- coding: utf-8 -*-
"""从 B站下载真实俄语人声音频（俄语听力/教学视频）"""

import json
import os
import time

import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
     "Referer": "https://www.bilibili.com/"}

proj = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.join(proj, "test_audio", "real")
os.makedirs(DEST, exist_ok=True)


def search(keyword, page=1):
    url = "https://api.bilibili.com/x/web-interface/search/type"
    params = {"search_type": "video", "keyword": keyword, "page": page}
    r = requests.get(url, params=params, headers=H, timeout=15)
    d = r.json()
    if d.get("code") != 0:
        print("搜索失败:", d.get("message"))
        return []
    return d.get("data", {}).get("result", []) or []


def get_cid(bvid):
    r = requests.get("https://api.bilibili.com/x/player/pagelist",
                     params={"bvid": bvid}, headers=H, timeout=15)
    d = r.json()
    if d.get("code") == 0 and d.get("data"):
        return d["data"][0]["cid"]
    return None


def get_audio_url(bvid, cid):
    url = "https://api.bilibili.com/x/player/playurl"
    params = {"bvid": bvid, "cid": cid, "fnval": 16, "fourk": 1}
    r = requests.get(url, params=params, headers=H, timeout=15)
    d = r.json()
    if d.get("code") != 0:
        print("playurl 失败:", d.get("message"))
        return None
    dash = d.get("data", {}).get("dash") or {}
    audios = dash.get("audio") or []
    if audios:
        return audios[0].get("baseUrl") or audios[0].get("base_url")
    return None


def main():
    keywords = ["俄语听力 日常对话", "俄语 慢速 听力", "俄语 口语 对话", "俄语 新闻 听力"]
    downloaded = 0
    for kw in keywords:
        try:
            results = search(kw)
        except Exception as e:
            print(f"搜索 {kw} 失败: {str(e)[:50]}")
            continue
        print(f"\n关键词「{kw}」: {len(results)} 结果")
        for v in results[:5]:
            bvid = v.get("bvid")
            title = (v.get("title") or "").replace('<em class="keyword">', "").replace("</em>", "")[:50]
            if not bvid:
                continue
            try:
                cid = get_cid(bvid)
                if not cid:
                    continue
                aurl = get_audio_url(bvid, cid)
                if not aurl:
                    print(f"  [{title}] 无音频流，跳过")
                    continue
                # 下载音频 m4s（前 3 分钟足够测试）
                r = requests.get(aurl, headers=H, timeout=30)
                if r.status_code == 200 and len(r.content) > 10000:
                    fn = os.path.join(DEST, f"bili_{downloaded}.m4s")
                    open(fn, "wb").write(r.content[:15_000_000])  # 限 15MB
                    with open(os.path.join(DEST, f"bili_{downloaded}.json"), "w", encoding="utf-8") as f:
                        json.dump({"bvid": bvid, "title": title}, f, ensure_ascii=False)
                    print(f"  ✓ [{title}] {len(r.content)/1e6:.1f}MB")
                    downloaded += 1
                else:
                    print(f"  [{title}] 下载失败 HTTP {r.status_code}")
            except Exception as e:
                print(f"  [{title}] 错误: {str(e)[:40]}")
            time.sleep(1)  # 礼貌限速
        if downloaded >= 10:
            break
    print(f"\n共下载 {downloaded} 段真实俄语人声")


if __name__ == "__main__":
    main()
