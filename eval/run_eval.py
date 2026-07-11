"""Routing eval (P0.3): target >=90% intent accuracy on 50 labeled queries.

Run:
  python eval/run_eval.py            # uses the LLM router (needs ANTHROPIC_API_KEY)
  python eval/run_eval.py --heuristic  # keyword fallback baseline, no API needed
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.orchestrator import ChatState, classify, classify_heuristic

EVAL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "routing_eval.jsonl")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--heuristic", action="store_true", help="use keyword fallback instead of LLM")
    args = ap.parse_args()

    cases = [json.loads(l) for l in open(EVAL_FILE, encoding="utf-8") if l.strip()]
    correct, misses = 0, []
    for c in cases:
        pred = classify_heuristic(c["text"]) if args.heuristic else classify(c["text"], ChatState())
        if pred["intent"] == c["intent"]:
            correct += 1
        else:
            misses.append((c["text"], c["intent"], pred["intent"]))

    acc = correct / len(cases)
    mode = "heuristic" if args.heuristic else "LLM router"
    print(f"[{mode}] routing accuracy: {correct}/{len(cases)} = {acc:.1%}  (target: >=90%)")
    if misses:
        print("\nMisses (text | expected | got):")
        for t, exp, got in misses:
            print(f"  - {t[:60]!r} | {exp} | {got}")
    sys.exit(0 if acc >= 0.9 else 1)


if __name__ == "__main__":
    main()
