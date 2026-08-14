# -*- coding: utf-8 -*-
"""下载 NLLB-200-distilled-600M 本地翻译模型（带断点续传 + 自动重试）"""

import os
import time

import requests

MIRRORS = ["https://hf-mirror.com", "https://huggingface.co"]
REPO = "facebook/nllb-200-distilled-600M"
DEST = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "models", "nllb-200-distilled-600M")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

FILES = [
    "config.json",
    "pytorch_model.bin",
    "tokenizer.json",
    "sentencepiece.bpe.model",
    "special_tokens_map.json",
]


def pick_mirror():
    for m in MIRRORS:
        try:
            r = requests.get(f"{m}/api/models/{REPO}", headers=HEADERS, timeout=10)
            if r.status_code == 200:
                return m
        except Exception:
            continue
    return None


def download(url, path):
    existing = os.path.getsize(path) if os.path.exists(path) else 0
    headers = dict(HEADERS)
    mode = "ab" if existing > 0 else "wb"
    if existing > 0:
        headers["Range"] = f"bytes={existing}-"
    with requests.get(url, headers=headers, stream=True, timeout=30) as r:
        if r.status_code == 416:
            print(f"  {os.path.basename(path)}: 已完整")
            return True
        r.raise_for_status()
        with open(path, mode) as fp:
            for chunk in r.iter_content(1024 * 256):
                if chunk:
                    fp.write(chunk)
        print(f"  {os.path.basename(path)}: {os.path.getsize(path)/1e6:.0f}MB")
        return True


def main():
    os.makedirs(DEST, exist_ok=True)
    for attempt in range(30):
        mirror = pick_mirror()
        if mirror:
            print(f"镜像可用: {mirror}")
            break
        print(f"网络不通，{10}s 后重试 ({attempt+1}/30)")
        time.sleep(10)
    else:
        print("30 次重试后仍无网络")
        return

    for f in FILES:
        path = os.path.join(DEST, f)
        if os.path.exists(path) and os.path.getsize(path) > 1024 and f != "pytorch_model.bin":
            print(f"跳过已有: {f}")
            continue
        for _ in range(5):
            try:
                print(f"[{f}]")
                url = f"{mirror}/{REPO}/resolve/main/{f}"
                if download(url, path):
                    break
            except Exception as e:
                print(f"  失败: {str(e)[:60]}，重试")
                time.sleep(5)
    print("NLLB 模型下载完成")


if __name__ == "__main__":
    main()
