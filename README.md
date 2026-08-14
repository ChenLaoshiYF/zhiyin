# 纸音 · 俄汉同传（电脑端）

> 纸音（Zhiyin），谐音「知音」：老师的俄语透过半透明的字幕纸窗，实时变成你眼前的中文。

给俄罗斯老师的网课配的实时字幕工具：抓取系统声音 → 俄语识别 → 中文翻译 → 悬浮字幕。
在 RTX 5070 Laptop（16GB 内存）上实测通过，GPU 加速识别 + 本地草稿毫秒级出字。

## 原理

```
系统音频 (WASAPI Loopback) → faster-whisper 识别 → 本地 NLLB 草稿(毫秒级) → DeepSeek 修正 → 悬浮字幕
```

- **音频采集**：WASAPI Loopback 抓系统输出（自动匹配默认扬声器），不依赖麦克风/虚拟声卡，兼容 Zoom、腾讯会议、俄语网课平台
- **俄语识别**：faster-whisper large-v3-turbo，GPU float16，按静音切句 + 碎片自动合并（一句话不会被切成碎片）
- **混合翻译（默认）**：本地 NLLB-600M 毫秒级出草稿 → DeepSeek 云端修正润色，术语表 + 近期译文上下文保证术语一致
- **字幕窗**（Hanako 暖纸风格）：俄汉同行对照、句句紧凑、长句自动换行不出框、滚动历史、穿透模式（内容区穿透、按钮区永远可点）
- **课堂记录**：自动存 Markdown 双语笔记（exe 旁「文稿」文件夹）

## 使用

**打包版（推荐）**：双击 `dist\俄汉同传\俄汉同传.exe`

**开发版**：双击 **`启动俄汉同传.vbs`**

1. 启动器里选翻译后端（四选一）：
   - **本地**（默认，混合模式）：本地 NLLB 毫秒级草稿 + 可选云端修正
   - **云端 API**：DeepSeek 等 OpenAI 兼容接口，点「检测模型」自动列出模型
   - **本地 Ollama**：免费不联网，需先装 Ollama
   - **极速**：专用翻译 API（百度/MyMemory）
2. 调字幕样式：俄文字号（小/标准/大/特大/最大）、底衬深浅（实时预览）
3. 课堂记录：勾选保存，可直接输入路径或选文件夹
4. 点「开始同传」

**字幕窗**：
- 右上角四键：**暂停**（真正暂停识别翻译）/ **交互**（切换穿透）/ **复位**（回底部居中）/ **退出**
- 右下角拖拽缩放；顶栏空白区拖动位置；任何尺寸下至少显示一行文字
- 穿透模式：内容区鼠标穿过（不挡课件），按钮区仍可点
- 全局热键 Ctrl+Shift+T：穿透/交互快速切换

**关闭方式**：字幕窗「退出」键 / Alt+F4 / 系统托盘图标「退出全部」/ 命令行 `python main.py --stop`

单实例保护：重复启动会被拒绝；找不到字幕窗时右键托盘选「显示字幕」。

首次启动加载模型约 20-30 秒（GPU）；之后即开即用。启动失败看同目录 `log.txt`。

## 配置（config.json）

| 字段 | 说明 |
|---|---|
| `asr.model` | 识别模型目录，默认 `models/faster-whisper-large-v3-turbo`，可改到外置盘 |
| `asr.compute_type` | **`float16`（RTX 50 系必选，Blackwell 上 int8 会报 cuBLAS NOT_SUPPORTED）** |
| `translate.backend` | `hybrid`（默认）/ `cloud` / `local` / `fast` |
| `translate.local_model` | 本地 NLLB 模型目录，默认 `models/nllb-200-distilled-600M` |
| `translate.refine` | 云端修正开关：本地草稿 + DeepSeek 润色（可单独关） |
| `translate.cloud.*` | 云端 API：provider / base_url / api_key / model（DeepSeek 已配好） |
| `save_transcript` | 是否保存双语文稿 |
| `transcript_dir` | 文稿保存目录，默认 exe 旁 `文稿\`（Markdown，可进 Obsidian） |
| `glossary` | 术语表（俄→中），注入翻译保证专名术语准确 |
| `audio.loopback_device` | `auto` 自动匹配默认扬声器，可填设备名关键字 |
| `ui.*` | 字号、透明度、窗口宽度、点击穿透 |

### 翻译后端说明

1. **本地（hybrid，默认）**：NLLB-600M 本地毫秒级草稿 → DeepSeek 云端修正。快且准，推荐
2. **云端 API**：直接 DeepSeek 翻译，质量最高，延迟约 1-4 秒/句
3. **本地 Ollama**：免费不联网，质量取决于本地模型
4. **极速**：专用翻译 API，最快但质量一般

## 网络说明

- 识别模型已下载到 `models/`（faster-whisper 约 1.6GB + NLLB 约 2.4GB）
- DeepSeek API 走官方接口；Ollama 走本机 11434
- 模型文件可整体迁移到外置盘，改 config 里的路径即可

## 已知限制

- V1 只做听译（俄→中单向），不做反向互动
- 云端修正延迟约 1-4 秒；本地草稿毫秒级（修正失败自动回退草稿）
- 识别按静音切句：停顿 1.2 秒以上出句，连续不停顿最长 12 秒兜底切分
- 测试时其他程序的声音会被一起采集（WASAPI 抓整个系统输出），上课时只开网课即可

## 测试

- `test_ui.py`：16 项 UI/链路功能回归（含穿透按钮区可点、暂停回调）
- `test_audio\real\`：12 段 B站真实俄语新闻人声，用于端到端验证
- `e2e_shot.ps1`：真实人声全链路测试 + 字幕窗截图
