"""Screenshot understanding (P1.2) — an INPUT ADAPTER, not a fourth agent.

Converts a seller-panel screenshot into a short text description that then
enters the normal five-stage flow like any typed message. Works with both
providers via llm.complete_vision().
"""
from __future__ import annotations

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
    return llm.complete_vision(SYSTEM, "Extract the issue from this screenshot.",
                               image_bytes, media_type).strip()
