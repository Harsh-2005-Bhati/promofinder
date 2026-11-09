"""Optional LLM judge. Providers: none, gemini, groq, anthropic, openai, custom (any OpenAI-compatible URL).

Contract: the LLM returns block indices only. Code converts indices -> times and re-validates (scoring.apply_llm).
Responses are cached by prompt hash; bad JSON -> one retry -> heuristic fallback.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request

from pydantic import BaseModel, Field, ValidationError

from .models import Promo
from .parser import Episode
from .prompts import SCHEMA, build_prompt, SYSTEM

ENV_KEYS = {"gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"), "groq": ("GROQ_API_KEY",),
            "anthropic": ("ANTHROPIC_API_KEY",), "openai": ("OPENAI_API_KEY",),
            "custom": ("LLM_API_KEY", "OPENAI_API_KEY")}
DEFAULT_MODELS = {"gemini": "gemini-2.5-flash", "groq": "llama-3.3-70b-versatile",
                  "anthropic": "claude-haiku-5-5", "openai": "gpt-4o-mini", "custom": None}


class Adjust(BaseModel):
    first_idx: int
    last_idx: int


class Judgement(BaseModel):
    candidate_id: str
    hook_score: int = Field(ge=1, le=5)
    cliffhanger_score: int = Field(ge=1, le=5)
    standalone_score: int = Field(ge=1, le=5)
    hook_text: str = ""
    cliffhanger_text: str = ""
    why: str = ""
    adjust: Adjust | None = None


class LLMProvider:
    name = "base"
    model = None

    def judge(self, prompt: str, schema: dict) -> dict:  # returns parsed JSON dict, raises ValueError on bad JSON
        raise NotImplementedError


class NoneProvider(LLMProvider):
    name = "none"

    def judge(self, prompt, schema):
        return {"judgments": []}


class HTTPStatusError(RuntimeError):
    def __init__(self, code, body):
        super().__init__(f"HTTP {code}: {body[:300]!r}")
        self.code = code


def _request(url: str, headers: dict, body: dict | None = None, timeout: int = 300) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise HTTPStatusError(e.code, e.read()) from None


def _post(url: str, headers: dict, body: dict, timeout: int = 300, tries: int = 4) -> dict:
    """POST with backoff on rate limits / overload (429, 500, 503) and timeouts: waits 15, 30, 60 s.
    Thinking models can take minutes per call, so the read timeout is 300 s."""
    for i in range(tries):
        try:
            return _request(url, headers, body, timeout)
        except HTTPStatusError as e:
            if e.code in (429, 500, 503) and i < tries - 1:
                time.sleep(15 * 2 ** i)
                continue
            raise
        except (TimeoutError, urllib.error.URLError) as e:
            if i < tries - 1 and ("timed out" in str(e).lower() or isinstance(e, TimeoutError)):
                time.sleep(15 * 2 ** i)
                continue
            raise


def extract_json(text: str) -> dict:
    t = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.M).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        i, j = t.find("{"), t.rfind("}")
        if i >= 0 and j > i:
            try:
                return json.loads(t[i:j + 1])
            except json.JSONDecodeError:
                pass
    raise ValueError("response is not valid JSON")


class HTTPProvider(LLMProvider):
    def __init__(self, api_key: str, model: str | None = None):
        self.key = api_key
        self.model = model or os.environ.get(f"{self.name.upper()}_MODEL") or DEFAULT_MODELS[self.name]

    def judge(self, prompt, schema):
        return extract_json(self.complete(prompt))


class GeminiProvider(HTTPProvider):
    name = "gemini"
    BASE = "https://generativelanguage.googleapis.com/v1beta"

    def list_models(self) -> list[str]:
        r = _request(f"{self.BASE}/models?pageSize=200", {"x-goog-api-key": self.key})
        return [m["name"].split("/", 1)[1] for m in r.get("models", [])
                if "generateContent" in m.get("supportedGenerationMethods", [])]

    def _fallback_model(self) -> str | None:
        """If the configured model is gone (404), pick the newest stable text 'flash' model the key can use."""
        def ver(n):
            m = re.search(r"gemini-(\d+(?:\.\d+)?)", n)
            return float(m.group(1)) if m else 0.0
        cands = [n for n in self.list_models() if "flash" in n and not any(
            x in n for x in ("preview", "exp", "lite", "tts", "image", "audio", "live", "thinking"))]
        return max(cands, key=ver) if cands else None

    def complete(self, prompt):
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}}
        try:
            r = _post(f"{self.BASE}/models/{self.model}:generateContent", {"x-goog-api-key": self.key}, body)
        except HTTPStatusError as e:
            alt = self._fallback_model() if e.code == 404 else None
            if not alt:
                raise
            self.model = alt
            r = _post(f"{self.BASE}/models/{self.model}:generateContent", {"x-goog-api-key": self.key}, body)
        return r["candidates"][0]["content"]["parts"][0]["text"]


class OpenAICompatProvider(HTTPProvider):
    name = "openai"
    url = "https://api.openai.com/v1/chat/completions"

    def __init__(self, api_key, model=None, base_url=None):
        super().__init__(api_key, model)
        base = base_url or os.environ.get(f"{self.name.upper()}_BASE_URL")
        if base:  # any OpenAI-compatible server: vLLM, Ollama, LM Studio, OpenRouter, Azure-style gateways...
            base = base.rstrip("/")
            self.url = base if base.endswith("/chat/completions") else base + "/chat/completions"

    def complete(self, prompt):
        body = {"model": self.model, "temperature": 0.2, "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]}
        try:
            r = _post(self.url, {"Authorization": f"Bearer {self.key}"}, body)
        except HTTPStatusError as e:
            if e.code != 400:
                raise
            body.pop("response_format")  # some compatible servers reject JSON mode; the prompt already asks for JSON
            r = _post(self.url, {"Authorization": f"Bearer {self.key}"}, body)
        return r["choices"][0]["message"]["content"]


class CustomProvider(OpenAICompatProvider):
    """Any OpenAI-compatible endpoint: --llm custom --base-url https://host/v1 --model NAME (key in LLM_API_KEY)."""
    name = "custom"

    def __init__(self, api_key, model=None, base_url=None):
        base_url = base_url or os.environ.get("LLM_BASE_URL")
        model = model or os.environ.get("LLM_MODEL")
        if not base_url or not model:
            raise ValueError("custom provider needs --base-url (or LLM_BASE_URL) and --model (or LLM_MODEL)")
        super().__init__(api_key, model, base_url)


class GroqProvider(OpenAICompatProvider):
    name = "groq"
    url = "https://api.groq.com/openai/v1/chat/completions"


class AnthropicProvider(HTTPProvider):
    name = "anthropic"

    def complete(self, prompt):
        r = _post("https://api.anthropic.com/v1/messages",
                  {"x-api-key": self.key, "anthropic-version": "2023-06-01"},
                  {"model": self.model, "max_tokens": 4000, "system": SYSTEM,
                   "messages": [{"role": "user", "content": prompt}]})
        return "".join(c.get("text", "") for c in r["content"] if c.get("type") == "text")


PROVIDERS = {"gemini": GeminiProvider, "groq": GroqProvider, "anthropic": AnthropicProvider,
             "openai": OpenAICompatProvider, "custom": CustomProvider}


def get_provider(name: str, api_key: str | None = None, model: str | None = None,
                 base_url: str | None = None) -> LLMProvider:
    if name == "none":
        return NoneProvider()
    if name not in PROVIDERS:
        raise ValueError(f"unknown provider {name}")
    key = api_key or next((os.environ[k] for k in ENV_KEYS[name] if os.environ.get(k)), None)
    if not key and name == "custom":
        key = "none"  # local servers (Ollama, vLLM) often need no key
    if not key:
        raise ValueError(f"no API key for {name}: set {' or '.join(ENV_KEYS[name])}")
    cls = PROVIDERS[name]
    if issubclass(cls, OpenAICompatProvider):
        return cls(key, model, base_url)
    return cls(key, model)


def parse_judgements(raw: dict, ids: set[str]) -> dict[str, dict]:
    out = {}
    items = raw.get("judgments") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        raise ValueError("missing 'judgments' list")
    for it in items:
        try:
            j = Judgement.model_validate(it)
        except ValidationError:
            continue  # drop malformed item; candidate keeps heuristic scores (flag llm_missing_judgement)
        if j.candidate_id in ids:
            out[j.candidate_id] = j.model_dump()
    return out


def judge_episode(provider: LLMProvider, ep: Episode, cands: list[Promo], cache_dir: str | None = None):
    """Returns ({candidate_id: judgement}, status) where status in ok|cached|fallback; None on failure."""
    prompt = build_prompt(ep, cands)
    h = hashlib.sha256((provider.name + str(provider.model) + prompt).encode()).hexdigest()[:16]
    ids = {p.id for p in cands}
    path = os.path.join(cache_dir, f"{provider.name}_{ep.num}.json") if cache_dir else None
    if path and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                c = json.load(f)
            if c.get("prompt_hash") == h:
                return parse_judgements(c["response"], ids), "cached"
        except Exception:
            pass
    for attempt in range(2):  # retry once
        try:
            raw = provider.judge(prompt, SCHEMA)
            js = parse_judgements(raw, ids)
            if path:
                os.makedirs(cache_dir, exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({"prompt_hash": h, "provider": provider.name, "model": provider.model,
                               "response": raw}, f, indent=1, ensure_ascii=False)
            return js, "ok"
        except Exception as ex:  # bad JSON, HTTP error, timeout
            last = ex
    ep.warnings.append(f"LLM judge failed after retry ({type(last).__name__}: {str(last)[:120]}); "
                       "using heuristic scores")
    return None, "fallback"
