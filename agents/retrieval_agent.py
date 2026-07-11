"""Retrieval Agent (P0.2).

Contract:
  answer(question, marketplace, language) -> {"found": bool, "answer": str, "citations": [...]}

Guarantees:
  - Every answer is grounded ONLY in retrieved chunks and carries citations.
  - If best-match distance > MAX_DISTANCE (or no hits), returns found=False and a
    polite "no official answer found" message — never a guess.
"""
from __future__ import annotations

import config
from agents import llm
from rag.store import PolicyStore

_store: PolicyStore | None = None


def store() -> PolicyStore:
    global _store
    if _store is None:
        _store = PolicyStore()
    return _store


NOT_FOUND = {
    "hinglish": (
        "Mujhe iska official policy answer nahi mila. 🙏 Galat guidance dene se behtar hai "
        "main seedha bol doon — is case mein aap marketplace ke official seller support "
        "ticket se poochhein. Aap chaahein to sawaal thoda alag tarike se poochh kar dekh sakte hain."
    ),
    "english": (
        "I couldn't find an official policy answer for this. Rather than guess, I'd suggest "
        "raising this with the marketplace's official seller support. You could also try "
        "rephrasing the question."
    ),
}

SYSTEM = """You are a support assistant for small Indian e-commerce sellers (Meesho / Amazon India).

Rules — these are hard constraints:
1. Answer ONLY from the policy excerpts provided in <context>. Never use outside knowledge for policy facts, numbers, or deadlines.
2. If the excerpts do not actually answer the question, reply with exactly: NO_ANSWER
3. Reply in the same language/register as the seller ({language}). Keep it simple — no jargon without explanation. Short paragraphs or short bullet lines.
4. End with a "Source:" line listing the doc name + section for each excerpt you actually used.
5. If a deadline or time window is involved, call it out explicitly and prominently.
6. Never invent order-specific facts. Never ask for passwords/OTPs/bank details.
7. Keep the reply under ~180 words. This is a chat on a phone."""


def answer(question: str, marketplace: str | None, language: str, history: list[dict] | None = None) -> dict:
    hits = store().query(question, marketplace=marketplace)
    good = [h for h in hits if h["distance"] <= config.MAX_DISTANCE]
    if not good:
        return {"found": False, "answer": NOT_FOUND.get(language, NOT_FOUND["english"]), "citations": []}

    context = "\n\n---\n\n".join(
        f"<excerpt doc=\"{h['doc_name']}\" section=\"{h['section']}\" marketplace=\"{h['marketplace']}\">\n{h['text']}\n</excerpt>"
        for h in good
    )
    msgs = list(history or [])
    msgs.append(
        {
            "role": "user",
            "content": f"<context>\n{context}\n</context>\n\nSeller's question: {question}",
        }
    )
    text = llm.complete(
        system=SYSTEM.format(language=language),
        messages=msgs,
        model=config.ANSWER_MODEL,
        max_tokens=600,
    ).strip()

    if text == "NO_ANSWER" or "NO_ANSWER" in text[:30]:
        return {"found": False, "answer": NOT_FOUND.get(language, NOT_FOUND["english"]), "citations": []}

    citations = [
        {"doc": h["doc_name"], "section": h["section"], "url": h["source_url"], "distance": round(h["distance"], 3)}
        for h in good
    ]
    return {"found": True, "answer": text, "citations": citations}
