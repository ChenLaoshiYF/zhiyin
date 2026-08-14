@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [俄汉同传] 安装本地翻译依赖（torch + transformers + NLLB 模型）
echo 首次会下载约 5GB（torch CUDA 版 + 模型），请耐心等待。
echo 如果你打算用云端翻译（Ollama / DeepSeek 等），不需要运行本脚本。
pause
".venv\Scripts\python.exe" -m pip install torch --index-url https://download.pytorch.org/whl/cu128
".venv\Scripts\python.exe" -m pip install transformers
pause
