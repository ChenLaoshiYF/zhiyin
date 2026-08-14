"""模型下载脚本：直接用 requests 从 hf-mirror 下载（绕开 huggingface_hub 的 HEAD 重定向问题）

用法：
    python download_model.py [repo_id] [目标目录]

默认：deepdml/faster-whisper-large-v3-turbo-ct2 -> models/faster-whisper-large-v3-turbo
"""

import os
import sys

MIRROR = "https://hf-mirror.com"

repo = sys.argv[1] if len(sys.argv) > 1 else "deepdml/faster-whisper-large-v3-turbo-ct2"
dest = sys.argv[2] if len(sys.argv) > 2 else "models/faster-whisper-large-v3-turbo"

import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def list_files(repo_id: str):
    r = requests.get(f"{MIRROR}/api/models/{repo_id}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    return [s["rfilename"] for s in data.get("siblings", [])]


def download(url: str, path: str):
    """断点续传下载单个文件；大小未知时无 Range 下载。"""
    existing = os.path.getsize(path) if os.path.exists(path) else 0
    headers = dict(HEADERS)
    mode = "ab"
    if existing > 0:
        headers["Range"] = f"bytes={existing}-"
    else:
        mode = "wb"
    with requests.get(url, headers=headers, stream=True, timeout=60) as r:
        # 416 说明文件已完整（Range 从 EOF 开始），视为成功
        if r.status_code == 416:
            print(f"  {os.path.basename(path)}: 已完整，跳过")
            return existing
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0) + existing
        written = existing
        with open(path, mode) as fp:
            for chunk in r.iter_content(1024 * 256):
                if chunk:
                    fp.write(chunk)
                    written += len(chunk)
        print(f"  {os.path.basename(path)}: {written/1e6:.0f} MB")
        return written


def main():
    os.makedirs(dest, exist_ok=True)
    files = list_files(repo)
    print(f"仓库 {repo} 共 {len(files)} 个文件，开始下载到 {dest}")
    for f in files:
        if f in (".gitattributes", "README.md"):
            continue
        url = f"{MIRROR}/{repo}/resolve/main/{f}"
        path = os.path.join(dest, f)
        print(f"[{f}]")
        try:
            download(url, path)
        except Exception as e:
            print(f"  失败: {e}，重试一次...")
            download(url, path)
    print("全部完成")


if __name__ == "__main__":
    main()
