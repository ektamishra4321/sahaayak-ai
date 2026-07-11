"""Action Agent (P0.4).

Drafts return-dispute claims, payment-hold emails, and listing-suppression appeals.

Slot-filling contract:
  - Each draft type declares mandatory fields.
  - The agent extracts fields from the conversation; if any mandatory field is
    missing it asks for ONE missing field at a time (never emits [PLACEHOLDER] drafts).
  - Before drafting, it calls the retrieval agent to pull relevant policy language
    so the draft cites policy (grounding).

State is kept by the orchestrator and passed in as `pending` (dict) per chat.
"""
from __future__ import annotations

import json

import config
from agents import llm, retrieval_agent

DRAFT_TYPES = {
    "return_dispute": {
        "label": "Return / RTO dispute claim",
        "fields": ["order_id", "issue_description"],
        "optional": ["awb_number", "return_date", "product_name"],
        "retrieval_hint": "return dispute wrong item used product claim window",
    },
    "payment_hold_email": {
        "label": "Payment hold enquiry email",
        "fields": ["issue_description"],
        "optional": ["order_id", "hold_since", "amount"],
        "retrieval_hint": "payment hold settlement cycle documents required",
    },
    "listing_appeal": {
        "label": "Listing suppression appeal",
        "fields": ["issue_description"],
        "optional": ["sku", "asin_or_listing_id", "error_message"],
        "retrieval_hint": "listing suppressed error appeal reinstate",
    },
}

FIELD_QUESTIONS = {
    "hinglish": {
        "order_id": "Theek hai! Order ID kya hai?",
        "issue_description": "Ek line mein batao — exact problem kya hai?",
        "awb_number": "Return AWB number pata hai? (nahi pata to 'skip' likho)",
    },
    "english": {
        "order_id": "Got it — what's the order ID?",
        "issue_description": "In one line, what exactly is the problem?",
        "awb_number": "Do you have the return AWB number? (type 'skip' if not)",
    },
}

EXTRACT_SYSTEM = """Extract structured fields for an e-commerce seller support draft from the conversation.
Return ONLY a JSON object, no prose, no markdown fences. Schema:
{"draft_type": one of ["return_dispute","payment_hold_email","listing_appeal"] or null,
 "marketplace": "meesho"|"amazon"|null,
 "fields": {<field_name>: <string value>}}
Only include fields explicitly stated by the seller. Never invent values.
Known field names: order_id, issue_description, awb_number, return_date, product_name, hold_since, amount, sku, asin_or_listing_id, error_message."""

DRAFT_SYSTEM = """You draft marketplace seller-support submissions for small Indian sellers.
Write the draft in clear, polite, professional ENGLISH (marketplace support panels expect English),
then add one short line in the seller's language ({language}) telling them where to paste it.

Hard rules:
- Use ONLY the field values provided. If a value is absent, do not mention it — NEVER write placeholders like [ORDER_ID].
- Weave in the provided policy excerpts (quote the policy point briefly, cite doc + section) to strengthen the case.
- Structure: greeting → issue summary with facts → policy basis → clear request → sign-off.
- Keep under 200 words. No emotional language; factual and firm.
- End with: "— Draft by SahaayakAI. Please review details before submitting.\""""


def extract(conversation_text: str) -> dict:
    """One LLM call: figure out draft type + fields mentioned so far."""
    raw = llm.complete(
        system=EXTRACT_SYSTEM,
        messages=[{"role": "user", "content": conversation_text}],
        model=config.ROUTER_MODEL,
        max_tokens=300,
    )
    try:
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"draft_type": None, "marketplace": None, "fields": {}}


def next_missing_field(draft_type: str, fields: dict) -> str | None:
    for f in DRAFT_TYPES[draft_type]["fields"]:
        if not fields.get(f):
            return f
    return None


def ask_for_field(field: str, language: str) -> str:
    table = FIELD_QUESTIONS.get(language, FIELD_QUESTIONS["english"])
    return table.get(field, f"Please share: {field.replace('_', ' ')}")


def make_draft(draft_type: str, marketplace: str | None, fields: dict, language: str) -> str:
    spec = DRAFT_TYPES[draft_type]
    rag = retrieval_agent.answer(
        question=f"{spec['retrieval_hint']} {fields.get('issue_description','')}",
        marketplace=marketplace,
        language="english",
    )
    policy_block = rag["answer"] if rag["found"] else "(no specific policy excerpt found — draft on facts only)"
    payload = {
        "draft_type": spec["label"],
        "marketplace": marketplace or "unspecified",
        "fields": {k: v for k, v in fields.items() if v},
        "policy_excerpts": policy_block,
    }
    return llm.complete(
        system=DRAFT_SYSTEM.format(language=language),
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        model=config.ANSWER_MODEL,
        max_tokens=700,
    ).strip()
