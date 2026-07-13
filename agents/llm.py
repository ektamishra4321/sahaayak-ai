"""Single place that talks to the LLM provider.

Supports two providers, selected by LLM_PROVIDER in .env:
  - "anthropic" : paid API, best quality (two model tiers)
  - "gemini"    : Google AI Studio free tier (~1,500 req/day on Flash, no card)

Everything else in the codebase calls complete() / complete_vision() and
never knows which provider is behind it.
"""
from __future__ import annotations

import base64
import json
import re

import httpx

import config


def parse_json_block(text: str) -> dict:
    """Extract the first JSON object from LLM output, tolerating prose,
    markdown fences, and trailing commentary (Gemini is chattier than Claude)."""
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"no JSON object in: {text[:80]!r}")
    return json.loads(m.group(0))

# ---------------------------------------------------------------- anthropic

_anthropic_client = None


def client():
    """Anthropic SDK client (kept for backward compat; anthropic-only)."""
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic
        _anthropic_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _anthropic_client


def _anthropic_complete(system: str, messages: list[dict], model: str, max_tokens: int) -> str:
    resp = client().messages.create(
        model=model, max_tokens=max_tokens, system=system, messages=messages
    )
    return "".join(b.text for b in resp.content if b.type == "text")


# ---------------------------------------------------------------- gemini

_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _to_gemini_contents(messages: list[dict]) -> list[dict]:
    """Map Anthropic-style messages to Gemini contents (assistant -> model)."""
    out = []
    for m in messages:
        role = "model" if m["role"] == "assistant" else "user"
        content = m["content"]
        parts = [{"text": content}] if isinstance(content, str) else content
        out.append({"role": role, "parts": parts})
    return out


_resolved_model: str | None = None


def _resolve_gemini_model() -> str:
    """Ask Google which models this key can use and pick the best Flash one.

    Model names churn (2.0 retired, 2.5/3.x rollouts vary by account), so on a
    404 we self-heal instead of hardcoding a name.
    """
    global _resolved_model
    if _resolved_model:
        return _resolved_model
    r = httpx.get("https://generativelanguage.googleapis.com/v1beta/models",
                  headers={"x-goog-api-key": config.GEMINI_API_KEY},
                  params={"pageSize": 200}, timeout=30)
    r.raise_for_status()
    models = [m["name"].removeprefix("models/") for m in r.json().get("models", [])
              if "generateContent" in m.get("supportedGenerationMethods", [])]
    if not models:
        raise RuntimeError("This Gemini key has no models supporting generateContent.")

    def score(name: str) -> tuple:
        n = name.lower()
        return ("flash" in n,                      # prefer flash family (free tier)
                "lite" not in n,                   # prefer full flash over lite
                "preview" not in n and "exp" not in n,  # prefer stable
                n)                                  # newest-ish by name sort
    _resolved_model = sorted(models, key=score, reverse=True)[0]
    return _resolved_model


def _gemini_call(system: str, contents: list[dict], max_tokens: int,
                 _model: str | None = None, _no_thinking_cfg: bool = False) -> str:
    model = _model or _resolved_model or config.GEMINI_MODEL
    gen_cfg = {"maxOutputTokens": max(max_tokens, 1200)}  # headroom: thinking eats budget
    if not _no_thinking_cfg:
        # disable internal "thinking" on models that support the knob: faster,
        # cheaper, and prevents reasoning fragments leaking into replies
        gen_cfg["thinkingConfig"] = {"thinkingBudget": 0}
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": gen_cfg,
    }
    def _post():
        return httpx.post(
            _GEMINI_URL.format(model=model),
            headers={"x-goog-api-key": config.GEMINI_API_KEY,
                     "Content-Type": "application/json"},
            json=body, timeout=120,
        )
    try:
        r = _post()
    except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError):
        r = _post()   # slow networks happen; one automatic retry
    if r.status_code == 404 and _model is None:
        # model name not available on this account -> discover and retry once
        return _gemini_call(system, contents, max_tokens,
                            _model=_resolve_gemini_model(), _no_thinking_cfg=_no_thinking_cfg)
    if r.status_code == 400 and not _no_thinking_cfg:
        # model doesn't accept thinkingConfig -> retry without it
        return _gemini_call(system, contents, max_tokens,
                            _model=model, _no_thinking_cfg=True)
    r.raise_for_status()
    data = r.json()
    try:
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if not text.strip():
            raise KeyError("empty")
        return text
    except (KeyError, IndexError):
        raise RuntimeError(f"Gemini returned no text (finishReason="
                           f"{data.get('candidates',[{}])[0].get('finishReason','?')})")


# ---------------------------------------------------------------- public API

def complete(system: str, messages: list[dict], model: str, max_tokens: int = 1024) -> str:
    if config.LLM_PROVIDER == "gemini":
        return _gemini_call(system, _to_gemini_contents(messages), max_tokens)
    return _anthropic_complete(system, messages, model, max_tokens)


def complete_vision(system: str, prompt: str, image_bytes: bytes,
                    media_type: str = "image/jpeg", max_tokens: int = 300) -> str:
    b64 = base64.standard_b64encode(image_bytes).decode()
    if config.LLM_PROVIDER == "gemini":
        contents = [{"role": "user", "parts": [
            {"inline_data": {"mime_type": media_type, "data": b64}},
            {"text": prompt},
        ]}]
        return _gemini_call(system, contents, max_tokens)
    resp = client().messages.create(
        model=config.ANSWER_MODEL, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
            {"type": "text", "text": prompt},
        ]}],
    )
    return "".join(b.text for b in resp.content if b.type == "text")
