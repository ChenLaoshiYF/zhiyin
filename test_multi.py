# -*- coding: utf-8 -*-
"""多段真实音频连续测试：依次播放 test_audio/real/ 下的全部 wav，
统计识别/翻译链路是否正常。需要 main.py --run 已在后台运行。

用法：
    1. 先启动字幕：pythonw main.py --run（或 exe --run）
    2. 再运行本脚本：python test_multi.py
"""
import glob
import os
import sys
import time

import soundfile as sf  # noqa: F401 (确保依赖存在提示)
import winsound

PROJECT = os.path.dirname(os.path.abspath(__file__))
REAL_DIR = os.path.join(PROJECT, "test_audio", "real")


def play_wav(path):
    winsound.PlaySound(path, winsound.SND_FILENAME)


def main():
    wavs = sorted(glob.glob(os.path.join(REAL_DIR, "real_*.wav")))
    if not wavs:
        print("test_audio/real/ 下没有 wav，先跑 download_bili2.py")
        return
    print(f"共 {len(wavs)} 段真实人声，开始连续播放（每段播完等 30 秒供翻译）")
    for i, w in enumerate(wavs, 1):
        name = os.path.basename(w)
        print(f"[{i}/{len(wavs)}] 播放 {name} ...")
        play_wav(w)
        time.sleep(30)
    print("全部播放完成。检查 log.txt 中的 [识别]/[翻译] 行确认链路。")


if __name__ == "__main__":
    main()
