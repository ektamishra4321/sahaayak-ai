"""Single place that talks to the LLM provider.

Supports two providers, selected by LLM_PROVIDER in .env:
  - "anthropic" : paid API, best quality (two model tiers)
  - "gemini"    : Google AI Studio free tier (~1,500 req/day on Flash, no card)

Everything else in the codebase calls complete() / complete_vision() and
never knows which provider is behind it.
"""
from __future__ import annotations

import base64

import httpx

import config

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


def _gemini_call(system: str, contents: list[dict], max_tokens: int) -> str:
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {"maxOutputTokens": max_tokens},
    }
    r = httpx.post(
        _GEMINI_URL.format(model=config.GEMINI_MODEL),
        headers={"x-goog-api-key": config.GEMINI_API_KEY,
                 "Content-Type": "application/json"},
        json=body, timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    try:
        return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
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
