"""Retrieval-quality eval (guards PRD Goal 5 against corpus regressions).

Two checks, both offline (no LLM key needed):
  1. Grounding: for labeled queries, the expected doc section must appear in
     the top-K retrieved chunks (hit@1 / hit@K reported; hit@K is the gate,
     because the answering model sees all K chunks).
  2. Refusal: out-of-corpus queries must score ABOVE the distance threshold,
     so the bot says "not found" instead of answering from a wrong chunk.

Run:  python eval/retrieval_eval.py        (after `python -m rag.ingest`)
Exit code 0 = pass (hit@K >= 90% AND all refusals correct).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from rag.store import PolicyStore

# (query, marketplace_filter, substring expected in doc_name or section of a top-K hit)
LABELED = [
    ("customer ne used product return kiya kya karun", "meesho", "Raising a Return Claim"),
    ("wrong item wapas aaya claim kaise karun", "meesho", "Raising a Return Claim"),
    ("return parcel tampered lag raha hai kya karun", "meesho", "Protect Yourself First"),
    ("unboxing video zaroori hai kya", "meesho", "Protect Yourself First"),
    ("rto aur customer return mein kya farak hai", "meesho", "RTO vs Customer Returns"),
    ("return window kitne din ki hoti hai", "meesho", "RTO vs Customer Returns"),
    ("claim approve hua paisa kab milega", "meesho", "Compensation"),
    ("damaged return ka kitna paisa milta hai", "meesho", "Compensation"),
    ("claim reject ho gaya ab kya karun", "meesho", "Rejected"),
    ("payment kitne din mein aata hai", "meesho", "Payment Cycle"),
    ("payment hold pe kyu hai", "meesho", "Held"),
    ("gst name mismatch se payment ruka hai", "meesho", "Resolving a Hold"),
    ("safe-t claim kya hota hai", "amazon", "SAFE-T"),
    ("safe-t claim kaise file karte hain", "amazon", "How to File"),
    ("safe-t claim ki deadline kya hai", "amazon", "Deadlines"),
    ("safe-t appeal kaise karun", "amazon", "Deadlines"),
    ("claim ke liye kya evidence chahiye", "amazon", "Evidence"),
    ("listing suppress kyu hui", "amazon", "Suppression"),
    ("suppressed listing kaise thik karun", "amazon", "Fixing and Appealing"),
    ("brand ip complaint se listing band hui", "amazon", "Fixing and Appealing"),
]

# Out-of-corpus queries, split by which brake must catch them:
NUMERIC_REFUSE = [           # far from corpus -> distance gate must refuse
    "aaj ka mausam kaisa hai delhi mein",
]
UPSTREAM_GUARD = [           # unsupported marketplace -> Stage-0 code guard
    "flipkart pe seller account kaise banate hain",   # (tested in pytest)
]
PROMPT_CONTRACT = [          # overlap zone (d ~0.6-0.8) -> NO_ANSWER contract
    "instagram ads kaise chalayein apni shop ke liye",  # verified in weekly manual audit
]


def main() -> None:
    store = PolicyStore()
    if store.count() == 0:
        sys.exit("Vector store is empty — run `python -m rag.ingest --reset` first.")

    hit1 = hitk = 0
    misses = []
    for q, mp, expected in LABELED:
        hits = store.query(q, marketplace=mp, top_k=config.TOP_K)
        labels = [f"{h['doc_name']} / {h['section']}" for h in hits]
        if any(expected.lower() in l.lower() for l in labels[:1]):
            hit1 += 1
        if any(expected.lower() in l.lower() for l in labels):
            hitk += 1
        else:
            misses.append((q, expected, labels[0] if labels else "NO HITS"))

    n = len(LABELED)
    print(f"Grounding  hit@1: {hit1}/{n} = {hit1/n:.0%}   hit@{config.TOP_K}: {hitk}/{n} = {hitk/n:.0%}  (gate: hit@{config.TOP_K} >= 90%)")
    for q, exp, got in misses:
        print(f"  MISS: {q!r}\n        expected ~{exp!r}, top hit: {got}")

    refusal_ok = 0
    for q in NUMERIC_REFUSE:
        best = store.query(q, top_k=1)
        d = best[0]["distance"] if best else 999
        ok = d > config.MAX_DISTANCE
        refusal_ok += ok
        print(f"Refusal    {'PASS' if ok else 'FAIL'}  d={d:.2f}  {q!r} (numeric gate)")
    for q in PROMPT_CONTRACT:
        d = store.query(q, top_k=1)[0]["distance"]
        print(f"Refusal    INFO  d={d:.2f}  {q!r} -> handled by NO_ANSWER prompt contract (audit weekly)")
    print(f"Refusal    NOTE  {len(UPSTREAM_GUARD)} unsupported-marketplace case(s) handled by Stage-0 code guard (pytest)")

    passed = (hitk / n >= 0.9) and refusal_ok == len(NUMERIC_REFUSE)
    print("RESULT:", "PASS" if passed else "FAIL")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
