"""Screenshot understanding (P1.2) — an INPUT ADAPTER, not a fourth agent.

A seller-panel screenshot is converted to a short text description of the
visible issue; that text then enters the normal five-stage flow like any
typed message. This module decides nothing — it only changes modality.

Contract:
  extract_issue(image_bytes, media_type) -> str
  - 1-3 lines describing the error/issue, order IDs, marketplace clues.
  - Returns the token IRRELEVANT_IMAGE if the image is not a seller-panel /
    e-commerce screenshot (selfies, memes, random photos).
  - NEVER transcribes credentials (passwords, OTPs, card numbers, full bank
    account numbers) even if visible in the screenshot.
"""
from __future__ import annotations

import base64

import config
from agents import llm

IRRELEVANT = "IRRELEVANT_IMAGE"

SYSTEM = """You read screenshots sent by small Indian e-commerce sellers (Meesho Supplier Panel, Amazon Seller Central, order/return/payment screens).

Extract, in 1-3 short lines of plain text:
- what screen/panel this is (if identifiable) and which marketplace
- the exact error message, status, or issue shown
- any order ID / SKU / claim ID / settlement ID visible

Hard rules:
- If the image is NOT a seller-panel or e-commerce related screenshot, reply with exactly: IRRELEVANT_IMAGE
- NEVER transcribe passwords, OTPs, CVVs, card numbers, or full bank account numbers, even if visible. Replace them with [hidden].
- No commentary, no advice — extraction only. The support flow handles the rest."""


def extract_issue(image_bytes: bytes, media_type: str = "image/jpeg") -> str:
    b64 = base64.standard_b64encode(image_bytes).decode()
    resp = llm.client().messages.create(
        model=config.ANSWER_MODEL,
        max_tokens=300,
        system=SYSTEM,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                {"type": "text", "text": "Extract the issue from this screenshot."},
            ],
        }],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()
