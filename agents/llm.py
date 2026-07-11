"""Single place that talks to the Anthropic API."""
from __future__ import annotations

import anthropic

import config

_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def complete(system: str, messages: list[dict], model: str, max_tokens: int = 1024) -> str:
    resp = client().messages.create(
        model=model, max_tokens=max_tokens, system=system, messages=messages
    )
    return "".join(block.text for block in resp.content if block.type == "text")
