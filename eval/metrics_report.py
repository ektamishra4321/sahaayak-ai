"""Weekly metrics + groundedness audit (PRD Section 8).

Usage:
  python eval/metrics_report.py           # metrics summary from logs
  python eval/metrics_report.py --audit   # also sample 30 policy answers for manual review

Reads data/logs/conversations.jsonl written by agents/telemetry.py.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys

LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "logs", "conversations.jsonl")


def load_rows() -> list[dict]:
    if not os.path.exists(LOG_FILE):
        sys.exit(f"No logs yet at {LOG_FILE} — talk to the bot first.")
    return [json.loads(l) for l in open(LOG_FILE, encoding="utf-8") if l.strip()]


def pct(n: int, d: int) -> str:
    return f"{n}/{d} = {n / d:.1%}" if d else "n/a"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", action="store_true", help="sample 30 policy answers for manual groundedness review")
    args = ap.parse_args()

    rows = load_rows()
    users = {r["chat"] for r in rows}
    policy = [r for r in rows if r["intent"] == "policy_query"]
    actions = [r for r in rows if r["intent"] == "action_request"]
    latencies = [r["latency_ms"] for r in rows if r["intent"] in ("policy_query", "action_request")]

    cited = [r for r in policy if r.get("grounded") is True]
    honest_nf = [r for r in policy if r.get("grounded") is False]
    drafts_done = [r for r in actions if "Draft by SahaayakAI" in (r.get("text_out") or "")]

    print("=" * 52)
    print("SahaayakAI — metrics report (PRD Section 8)")
    print("=" * 52)
    print(f"Total messages handled : {len(rows)}")
    print(f"Unique users           : {len(users)}   (target: 2-3 active weekly)")
    print(f"Policy queries         : {len(policy)}")
    print(f"  cited answers        : {pct(len(cited), len(policy))}")
    print(f"  honest 'not found'   : {pct(len(honest_nf), len(policy))}")
    print(f"  cited OR honest      : {pct(len(cited) + len(honest_nf), len(policy))}   (target: 100%)")
    print(f"Action requests        : {len(actions)}")
    print(f"  completed drafts     : {pct(len(drafts_done), len(actions))}   (target: >=70%)")
    if latencies:
        print(f"Median time-to-answer  : {statistics.median(latencies)/1000:.1f}s   (target: <15s)")
    guard = sum(1 for r in rows if r.get("event") == "credential_guard")
    print(f"Credential-guard hits  : {guard}")
    up = sum(1 for r in rows if r.get("event") == "feedback_up")
    down = sum(1 for r in rows if r.get("event") == "feedback_down")
    if up + down:
        print(f"Feedback (P1.4)        : {up} 👍 / {down} 👎  = {up/(up+down):.0%} positive")

    if args.audit:
        sample = random.sample(policy, min(30, len(policy)))
        print("\n" + "=" * 52)
        print(f"GROUNDEDNESS AUDIT — review these {len(sample)} answers manually")
        print("For each: is every policy fact traceable to the cited doc? Mark PASS/FAIL.")
        print("=" * 52)
        for i, r in enumerate(sample, 1):
            print(f"\n[{i}] Q: {r['text_in']}")
            print(f"    A: {r['text_out'][:300]}")
            print(f"    grounded={r['grounded']}  citations={r['n_citations']}")


if __name__ == "__main__":
    main()
