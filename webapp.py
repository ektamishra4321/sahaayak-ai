"""SahaayakAI web app — the same agents, on a website.

The orchestrator is channel-agnostic by design; this is channel #2 (after
Telegram). Serves the landing page with a LIVE chat wired to the real bot.

Run:   python webapp.py        ->  http://localhost:8000
Needs: pip install flask  (and the usual .env + ingested corpus)
"""
from __future__ import annotations

import logging
import os
import re

from flask import Flask, jsonify, request, send_from_directory

from agents import orchestrator

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
log = logging.getLogger("sahaayak.web")

app = Flask(__name__, static_folder="web", static_url_path="")


@app.get("/")
def index():
    return send_from_directory("web", "index.html")


@app.post("/api/chat")
def chat():
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get("message") or "").strip()[:2000]
    raw_id = re.sub(r"[^a-zA-Z0-9_-]", "", str(data.get("chat_id") or ""))[:40]
    chat_id = f"web-{raw_id or 'anon'}"
    if not text:
        return jsonify({"reply": "Kuch likho to sahi! 🙂"})
    log.info("chat=%s in=%r", chat_id, text[:80])
    try:
        reply = orchestrator.handle_message(chat_id, text)
    except Exception:
        log.exception("web handler failed")
        reply = "Kuch technical problem aa gayi 😅 — thodi der mein dobara try karo."
    return jsonify({"reply": reply})


@app.get("/health")
def health():
    return {"ok": True}


if __name__ == "__main__":
    print("\n  SahaayakAI web app -> open http://localhost:8000 in your browser\n")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=False)
