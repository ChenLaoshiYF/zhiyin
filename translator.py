# -*- coding: utf-8 -*-
"""俄→中翻译：可插拔后端，支持流式输出

- cloud: 本地 Ollama 原生 API（think:false）或任意 OpenAI 兼容 API
- local: NLLB-200 本地翻译（需要 torch，install_nllb.bat）
- auto: cloud 优先，失败降级 local

流式：translate_stream(text, on_token) 边生成边推送增量，减少感知延迟。
术语表与近期译文上下文注入 system prompt，保证术语一致性。
"""

import os
import threading
import time

# 云端翻译基础 prompt
_SYSTEM_PROMPT = (
    "你是专业的俄语到简体中文翻译。把用户的俄语翻译成准确、自然、通顺的中文。"
    "如果是学术或专业术语，务必使用标准译法。只输出译文本身，不要任何解释、"
    "引号或额外内容。"
)


class BaseTranslator:
    def available(self) -> bool:
        raise NotImplementedError

    def translate(self, text: str, system_prompt: str = None) -> str:
        raise NotImplementedError

    def translate_stream(self, text: str, on_token, system_prompt: str = None) -> str:
        # 默认一次性翻译（子类可覆盖为真正的流式）
        return self.translate(text, system_prompt=system_prompt)


class CloudTranslator(BaseTranslator):
    """云端翻译：Ollama 原生 API 或 OpenAI 兼容 API，均支持流式。"""

    def __init__(self, base_url, api_key, model, provider="ollama"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.provider = provider
        self._ok = False
        self._checking = False
        self._check_lock = threading.Lock()

    def available(self) -> bool:
        if self._ok or self._checking:
            return self._ok
        with self._check_lock:
            if self._checking:
                return self._ok
            self._checking = True
            try:
                import requests
                if self.provider == "ollama":
                    r = requests.get(f"{self.base_url}/api/tags", timeout=5)
                    self._ok = r.status_code == 200
                else:
                    r = requests.get(f"{self.base_url}/models",
                                     headers={"Authorization": f"Bearer {self.api_key}"},
                                     timeout=5)
                    self._ok = r.status_code == 200
            except Exception:
                self._ok = False
            self._checking = False
            return self._ok

    def _messages(self, text, system_prompt):
        return [
            {"role": "system", "content": system_prompt or _SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ]

    def translate(self, text: str, system_prompt: str = None) -> str:
        if self.provider == "ollama":
            return self._ollama(text, system_prompt, stream=False)
        return self._openai(text, system_prompt, stream=False)

    def translate_stream(self, text: str, on_token, system_prompt: str = None) -> str:
        if self.provider == "ollama":
            return self._ollama(text, system_prompt, stream=True, on_token=on_token)
        return self._openai(text, system_prompt, stream=True, on_token=on_token)

    def _ollama(self, text, system_prompt, stream, on_token=None):
        import json
        import requests
        payload = {
            "model": self.model,
            "messages": self._messages(text, system_prompt),
            "stream": stream,
            "options": {"temperature": 0.1, "num_predict": 256},
            "think": False,  # qwen3.5 等推理模型必须关思考，否则 content 为空
        }
        r = requests.post(f"{self.base_url}/api/chat", json=payload,
                          stream=stream, timeout=90)
        r.raise_for_status()
        if not stream:
            content = r.json().get("message", {}).get("content", "")
            return content.strip() if content else f"[翻译空] {text}"
        full = ""
        for line in r.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            delta = (d.get("message") or {}).get("content") or ""
            if delta:
                full += delta
                if on_token:
                    on_token(full)
        return full.strip()

    def _openai(self, text, system_prompt, stream, on_token=None, max_tokens=1024):
        import json
        import requests
        payload = {
            "model": self.model,
            "messages": self._messages(text, system_prompt),
            "temperature": 0.1,
            "max_tokens": max_tokens,  # 推理模型 reasoning 会消耗配额，给足余量
            "stream": stream,
        }
        r = requests.post(f"{self.base_url}/chat/completions",
                          headers={"Authorization": f"Bearer {self.api_key}"},
                          json=payload, stream=stream, timeout=25)
        r.raise_for_status()
        if not stream:
            content = ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            content = content.strip()
            return content if content else f"[译文缺失] {text}"
        full = ""
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            s = line[5:].strip()
            if s == "[DONE]":
                break
            try:
                d = json.loads(s)
            except json.JSONDecodeError:
                continue
            delta = d.get("choices", [{}])[0].get("delta", {}).get("content") or ""
            if delta:
                full += delta
                if on_token:
                    on_token(full)
        if not full.strip():
            # 推理模型把配额吃光导致 content 为空：重试两次（非流式 + 更大配额）
            print("[翻译] 警告: 响应为空，重试非流式")
            try:
                retry = self._openai(text, system_prompt, stream=False, on_token=None)
                if retry and not retry.startswith("[译文缺失]"):
                    return retry
            except Exception as e:
                print(f"[翻译] 重试1失败: {e}")
            print("[翻译] 警告: 再次重试")
            try:
                return self._openai(text, system_prompt, stream=False, on_token=None)
            except Exception as e:
                print(f"[翻译] 重试2失败: {e}")
                return f"[译文缺失] {text}"
        return full.strip()

    def refine(self, text: str, draft: str) -> str:
        """云端修正本地草稿：原文 + 初稿一起给大模型润色。"""
        prompt = (
            "这是俄语原文和机器翻译的初稿译文。请把初稿修正为准确、自然、通顺的中文，"
            "学术/专业术语务必使用标准译法。只输出修正后的译文，不要解释。\n\n"
            f"俄语原文：{text}\n\n初稿译文：{draft}"
        )
        last_err = None
        for attempt in range(2):
            try:
                if self.provider == "ollama":
                    result = self._ollama(prompt, _SYSTEM_PROMPT, stream=False)
                else:
                    result = self._openai(prompt, _SYSTEM_PROMPT, stream=False,
                                          max_tokens=2048)
                if result and not result.startswith("[译文缺失]"):
                    return result
                last_err = "修正响应为空"
            except Exception as e:
                last_err = str(e)
            print(f"[修正] 第{attempt + 1}次失败: {last_err}")
            time.sleep(0.5)
        raise RuntimeError(last_err or "修正失败")


class FastTranslator(BaseTranslator):
    """极速翻译：专用翻译 API（非大模型），毫秒级响应。

    provider = "baidu"：百度翻译开放平台（需 appid/secret，免费额度）
    provider = "mymemory"：MyMemory 免费 API（无需 key，质量一般）
    """

    def __init__(self, appid="", secret="", provider="mymemory"):
        self.appid = appid
        self.secret = secret
        self.provider = provider
        self._ok = None

    def available(self) -> bool:
        if self._ok is not None:
            return self._ok
        if self.provider == "baidu":
            self._ok = bool(self.appid and self.secret)
        else:
            self._ok = True  # MyMemory 无需配置
        return self._ok

    def translate(self, text: str, system_prompt: str = None) -> str:
        import hashlib
        import random
        import urllib.parse
        import requests
        if self.provider == "baidu":
            salt = str(random.randint(32768, 65536))
            sign = hashlib.md5(
                f"{self.appid}{text}{salt}{self.secret}".encode("utf-8")
            ).hexdigest()
            r = requests.post(
                "https://fanyi-api.baidu.com/api/trans/vip/translate",
                data={"q": text, "from": "ru", "to": "zh",
                      "appid": self.appid, "salt": salt, "sign": sign},
                timeout=8,
            )
            r.raise_for_status()
            d = r.json()
            if d.get("error_code"):
                raise RuntimeError(f"百度翻译: {d.get('error_msg')}")
            return d["trans_result"][0]["dst"].strip()
        # MyMemory
        url = ("https://api.mymemory.translated.net/get?q="
               + urllib.parse.quote(text) + "&langpair=ru|zh-CN")
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        r.raise_for_status()
        d = r.json()
        txt = d.get("responseData", {}).get("translatedText", "")
        return txt.strip() if txt else f"[译文缺失] {text}"


class LocalNLLBTranslator(BaseTranslator):
    """NLLB-200-distilled-600M 本地翻译（需要 torch + transformers）。"""

    def __init__(self, model_name="facebook/nllb-200-distilled-600M"):
        self.model_name = model_name
        self._model = None
        self._tokenizer = None
        self._ok = None
        self._lock = threading.Lock()  # 并行翻译时只加载一次
        self._infer_lock = threading.Lock()  # NLLB 推理非线程安全，串行化

    def available(self) -> bool:
        """可用 = 库齐 + 模型文件完整（损坏/未下完不算）。"""
        if self._ok is not None:
            return self._ok
        try:
            import torch  # noqa: F401
            import transformers  # noqa: F401
        except ImportError:
            self._ok = False
            return self._ok
        # 本地目录模型：校验权重文件完整性
        if os.path.isdir(self.model_name):
            bin_path = os.path.join(self.model_name, "pytorch_model.bin")
            if not os.path.isfile(bin_path) or os.path.getsize(bin_path) < 1_000_000_000:
                print(f"[NLLB] 模型文件不完整，跳过本地翻译: {bin_path}")
                self._ok = False
                return self._ok
        self._ok = True
        return self._ok

    def _load(self):
        with self._lock:
            if self._model is None:
                import torch
                from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
                print(f"[翻译] 加载本地 NLLB 模型 {self.model_name} ...")
                self._tokenizer = AutoTokenizer.from_pretrained(self.model_name, src_lang="rus_Cyrl")
                self._model = AutoModelForSeq2SeqLM.from_pretrained(self.model_name)
                if torch.cuda.is_available():
                    self._model = self._model.half().cuda()
                self._device = "cuda" if torch.cuda.is_available() else "cpu"
                print("[翻译] NLLB 模型加载完成")
            elif not hasattr(self, "_device"):
                import torch
                self._device = "cuda" if torch.cuda.is_available() else "cpu"

    def translate(self, text: str, system_prompt: str = None) -> str:
        import torch
        if self._model is None or not hasattr(self, "_device"):
            self._load()
        # NLLB 推理非线程安全（CUDA borrow 冲突），整段串行
        with self._infer_lock:
            inputs = self._tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
            inputs = {k: v.to(self._device) for k, v in inputs.items()}
            with torch.no_grad():
                generated = self._model.generate(
                    **inputs,
                    forced_bos_token_id=self._tokenizer.convert_tokens_to_ids("zho_Hans"),
                    max_new_tokens=256,
                )
            return self._tokenizer.batch_decode(generated, skip_special_tokens=True)[0]


class TranslatorManager:
    """统一入口：按配置选后端，注入术语表与译文上下文，支持流式。"""

    def __init__(self, cfg: dict):
        t = cfg.get("translate", {})
        self.backend = t.get("backend", "auto")
        self.cloud = None
        self.local = None
        self.fast = None
        cloud_cfg = t.get("cloud", {})
        if cloud_cfg.get("base_url"):
            self.cloud = CloudTranslator(
                cloud_cfg["base_url"], cloud_cfg.get("api_key", ""), cloud_cfg.get("model", ""),
                provider=cloud_cfg.get("provider", "ollama"),
            )
        fast_cfg = t.get("fast", {})
        self.fast = FastTranslator(
            appid=fast_cfg.get("appid", ""),
            secret=fast_cfg.get("secret", ""),
            provider=fast_cfg.get("provider", "mymemory"),
        )
        self.local = LocalNLLBTranslator(t.get("local_model", "models/nllb-200-distilled-600M"))
        self.glossary = cfg.get("glossary", {})
        self.refine = t.get("refine", True)  # 独立开关：云端修正本地草稿
        self._ctx_zh = []
        self._ctx_lock = threading.Lock()
        self._cur = None

    def add_context(self, zh: str):
        """记录近期译文，注入后续翻译保持术语一致（最多 2 句）。

        调用方（pipeline）保证并发安全：翻译完成结果已在单线程侧按 seq 排序。
        """
        with self._ctx_lock:
            self._ctx_zh.append(zh)
            if len(self._ctx_zh) > 2:
                self._ctx_zh.pop(0)

    def _system_prompt(self) -> str:
        parts = [_SYSTEM_PROMPT]
        if self.glossary:
            terms = "；".join(f"{ru} → {zh}" for ru, zh in self.glossary.items())
            parts.append("术语对照（务必使用标准译法）：" + terms)
        if self._ctx_zh:
            parts.append("近期译文上下文（保持术语与风格一致）：" + " | ".join(self._ctx_zh))
        return "\n\n".join(parts)

    def pick(self):
        if self._cur is not None:
            return self._cur
        # 极速模式：专用翻译 API（毫秒级）
        if self.backend == "fast" and self.fast is not None and self.fast.available():
            self._cur = self.fast
            print("[翻译] 使用极速翻译")
            return self._cur
        if self.backend in ("auto", "cloud") and self.cloud is not None and self.cloud.available():
            self._cur = self.cloud
            print("[翻译] 使用云端翻译")
            return self._cur
        if self.backend == "auto" and self.cloud is None:
            print("[翻译] 未配置云端，尝试本地 NLLB")
        if self.local is not None and self.local.available():
            self._cur = self.local
            print("[翻译] 使用本地 NLLB 翻译")
            return self._cur
        if self.cloud is not None and self.cloud.available():
            self._cur = self.cloud
            print("[翻译] 使用云端翻译")
            return self._cur
        print("[翻译] 警告：没有可用的翻译后端")
        return None

    def translate(self, text: str) -> str:
        tr = self.pick()
        if tr is None:
            return f"[未翻译] {text}"
        try:
            return tr.translate(text, system_prompt=self._system_prompt())
        except Exception as e:
            print(f"[翻译] 失败: {e}")
            if self.backend == "auto":
                alt = self.local if tr is self.cloud else self.cloud
                if alt is not None and alt.available():
                    try:
                        return alt.translate(text, system_prompt=self._system_prompt())
                    except Exception as e2:
                        print(f"[翻译] 降级后端也失败: {e2}")
            return f"[翻译失败] {text}"

    def translate_stream(self, text: str, on_token) -> str:
        tr = self.pick()
        if tr is None:
            on_token(text)
            return text
        try:
            return tr.translate_stream(text, on_token, system_prompt=self._system_prompt())
        except Exception as e:
            print(f"[翻译] 流式失败，回退一次性: {e}")
            try:
                return tr.translate(text, system_prompt=self._system_prompt())
            except Exception as e2:
                print(f"[翻译] 降级也失败: {e2}")
                return f"[翻译失败] {text}"

    def translate_hybrid(self, text: str, on_draft=None, on_final=None) -> str:
        """混合翻译：本地 NLLB 毫秒级出草稿 →（开关开启时）云端修正。

        on_draft(draft)：本地草稿就绪时回调（字幕立即显示）
        on_final(final)：最终译文（修正后或草稿）
        """
        if self.local is not None and self.local.available():
            try:
                draft = self.local.translate(text)
                if on_draft:
                    on_draft(draft)
                print(f"[本地] {draft}")
            except Exception as e:
                print(f"[翻译] 本地翻译失败，回退云端: {e}")
                return self._cloud_fallback(text, on_final or on_draft)
            # 云端修正开关
            if self.refine and self.cloud is not None and self.cloud.available():
                try:
                    refined = self.cloud.refine(text, draft)
                    if on_final:
                        on_final(refined)
                    print(f"[修正] {refined}")
                    return refined
                except Exception as e:
                    print(f"[修正] 云端修正失败，保留草稿: {e}")
                    return draft
            return draft
        # 本地模型不可用 → 直接云端
        return self._cloud_fallback(text, on_final or on_draft)

    def _cloud_fallback(self, text, on_token):
        """云端直翻（流式），供本地不可用时兜底。"""
        return self.translate_stream(text, on_token or (lambda acc: None))
