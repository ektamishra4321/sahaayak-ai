"""Conversation telemetry (enables PRD metrics + weekly groundedness audit).

Appends one JSON line per handled message to data/logs/conversations.jsonl:
  {ts, chat, intent, language, marketplace, latency_ms, grounded, n_citations,
   text_in, text_out}

Privacy notes:
- chat_id is stored as a short salted hash, never raw, so logs can't be tied
  back to a Telegram account without the salt.
- Credential-guard hits log the EVENT but never the message text.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "logs")
LOG_FILE = os.path.join(LOG_DIR, "conversations.jsonl")
_SALT = os.getenv("LOG_SALT", "sahaayak-dev-salt")


def _hash_chat(chat_id: str) -> str:
    return hashlib.sha256(f"{_SALT}:{chat_id}".encode()).hexdigest()[:12]


def log_turn(
    chat_id: str,
    text_in: str,
    text_out: str,
    intent: str,
    language: str,
    marketplace: str | None,
    latency_ms: int,
    grounded: bool | None = None,      # True=cited, False=explicit not-found, None=n/a
    n_citations: int = 0,
    event: str | None = None,          # e.g. "credential_guard", "rate_limit"
) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    row: dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "chat": _hash_chat(chat_id),
        "intent": intent,
        "language": language,
        "marketplace": marketplace,
        "latency_ms": latency_ms,
        "grounded": grounded,
        "n_citations": n_citations,
        "event": event,
        # never store message content for credential events
        "text_in": None if event == "credential_guard" else text_in[:500],
        "text_out": text_out[:800],
    }
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
