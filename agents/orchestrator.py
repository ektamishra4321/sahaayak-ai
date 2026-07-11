"""Orchestrator (P0.3 + P0.5).

Responsibilities:
  1. Safety pre-checks (credential detection) — before anything else.
  2. Intent classification: policy_query | action_request | other.
  3. Language detection: hinglish | english.
  4. Conversation state per chat (history + pending action slots + rate limit).
  5. Route to retrieval agent or action agent; compose final reply.

Classification uses a cheap LLM call with a deterministic keyword fallback, so the
bot still routes sensibly if the router call fails.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

import config
from agents import llm, retrieval_agent, action_agent, telemetry, persistence

# ---------------------------------------------------------------- state

@dataclass
class ChatState:
    history: list[dict] = field(default_factory=list)   # [{"role","content"}]
    pending_action: dict | None = None                  # {"draft_type","marketplace","fields"}
    awaiting_field: str | None = None                   # slot the bot just asked for
    language: str = "hinglish"
    marketplace: str | None = None
    msg_timestamps: list[float] = field(default_factory=list)


_chats: dict[str, ChatState] = {}


def state_for(chat_id: str) -> ChatState:
    if chat_id not in _chats:
        saved = persistence.load_state(chat_id)
        _chats[chat_id] = ChatState(**saved) if saved else ChatState()
    return _chats[chat_id]


def _persist(chat_id: str, st: ChatState) -> None:
    persistence.save_state(chat_id, {
        "history": st.history,
        "pending_action": st.pending_action,
        "awaiting_field": st.awaiting_field,
        "language": st.language,
        "marketplace": st.marketplace,
        "msg_timestamps": st.msg_timestamps,
    })


# ---------------------------------------------------------------- safety (P0.5)

CREDENTIAL_PATTERNS = [
    re.compile(r"\botp\b.{0,12}\d{4,8}", re.I),
    re.compile(r"\bpassword\b\s*[:\-]?\s*\S+", re.I),
    re.compile(r"\bcvv\b\s*[:\-]?\s*\d{3,4}", re.I),
    re.compile(r"\b\d{9,18}\b.{0,20}\bifsc\b|\bifsc\b.{0,20}\b\d{9,18}\b", re.I),
]

CREDENTIAL_WARNING = {
    "hinglish": (
        "⚠️ Ruko! Aapne abhi password/OTP/bank detail jaisi cheez bheji hai. "
        "Main ye kabhi store ya use nahi karta, aur aapko bhi kisi bot ya insaan ko "
        "ye kabhi nahi dena chahiye — official app ke alawa kahin nahi. "
        "Message dobara bina us detail ke bhejo. 🙏"
    ),
    "english": (
        "⚠️ Hold on — that message looks like it contains a password/OTP/bank detail. "
        "I never store or use these, and you should never share them with any bot or person "
        "outside the official app. Please resend your message without that detail."
    ),
}

UNSUPPORTED_MARKETPLACES = ("flipkart", "myntra", "ajio", "snapdeal", "ebay", "etsy", "nykaa")

UNSUPPORTED_MP_MSG = {
    "hinglish": ("Abhi main sirf *Meesho* aur *Amazon India* ke seller issues cover karta hoon. "
                 "Flipkart/Myntra jaise platforms ka official answer mere paas nahi hai — "
                 "unke apne seller support se poochhna sahi rahega. 🙏"),
    "english": ("Right now I only cover *Meesho* and *Amazon India* seller issues. "
                "For other platforms, please check their own seller support."),
}

INTRO = (
    "Namaste! 🙏 Main *SahaayakAI* hoon — Meesho aur Amazon India sellers ka support assistant.\n\n"
    "Aap mujhse ye sab poochh sakte ho:\n"
    "1️⃣ \"Customer ne 15 din baad return kiya, accept karna padega?\"\n"
    "2️⃣ \"Mera payment hold pe hai, kya karun?\"\n"
    "3️⃣ \"Return claim ka draft bana do, order ID XXXXX\"\n\n"
    "⚠️ Note: main sirf *draft* banata hoon — submit aap khud review karke karoge. "
    "Kabhi bhi mujhe (ya kisi ko bhi) password/OTP mat bhejna."
)

OFF_TOPIC = {
    "hinglish": "Main sirf Meesho/Amazon seller issues mein madad karta hoon — returns, payments, listings, claims. Us bare mein poochho! 🙂",
    "english": "I only help with Meesho/Amazon seller issues — returns, payments, listings, claims. Ask me about those! 🙂",
}

RATE_LIMIT_MSG = {
    "hinglish": "Aaj ke liye message limit ho gayi. Kal phir baat karte hain! 🙏",
    "english": "You've hit today's message limit. Let's continue tomorrow! 🙏",
}

# ---------------------------------------------------------------- routing (P0.3)

ROUTER_SYSTEM = """Classify a message from an Indian e-commerce seller. Return ONLY JSON:
{"intent": "policy_query" | "action_request" | "other",
 "language": "hinglish" | "english",
 "marketplace": "meesho" | "amazon" | null}

Definitions:
- policy_query: asking what a rule/policy/process/deadline is, why something happened, what to do.
- action_request: asking you to DRAFT/WRITE something (claim, appeal, email, application) or continuing to provide details for a draft in progress.
- other: greetings, thanks, abuse, off-topic (weather, jokes, personal chat).
- language "hinglish" if the message uses any romanized Hindi; "english" if fully English. Devanagari also => "hinglish".
- marketplace only if stated or clearly implied in THIS message or the provided context; else null.
Context (may be empty): {context}"""

ACTION_KEYWORDS = ("draft", "bana do", "banao", "likh do", "likho", "write", "email bhejna", "claim file", "apply")
POLICY_KEYWORDS = ("policy", "kya karun", "kaise", "kyun", "why", "how", "kitne din", "deadline", "hold", "return", "payment", "listing", "claim", "penalty", "rto")
GREETING_KEYWORDS = ("hi", "hello", "namaste", "hey", "thanks", "thank you", "shukriya",
                     "dhanyavad", "good morning", "good evening", "bye", "ok bye", "kaise ho",
                     "kya haal", "tum kaun", "who are you", "joke", "mausam", "weather")


def classify_heuristic(text: str) -> dict:
    """Deterministic fallback — also used by the eval as a baseline."""
    t = text.lower().strip()
    lang = "english" if not re.search(
        r"\b(hai|karo|kya|nahi|mera|bana|kaise|kyun|karna|wala|bhai|din|paisa|hua|gaya|do)\b", t
    ) and not re.search(r"[\u0900-\u097F]", t) else "hinglish"
    mp = "meesho" if "meesho" in t else ("amazon" if "amazon" in t else None)
    if any(t == k or t.startswith(k + " ") or t.endswith(" " + k) or t == k.rstrip() for k in GREETING_KEYWORDS) or len(t) < 4:
        intent = "other"
    elif any(k in t for k in ACTION_KEYWORDS):
        intent = "action_request"
    elif any(k in t for k in POLICY_KEYWORDS):
        intent = "policy_query"
    else:
        intent = "policy_query"  # default: try to help
    return {"intent": intent, "language": lang, "marketplace": mp}


def classify(text: str, ctx: ChatState) -> dict:
    context = ""
    if ctx.pending_action:
        context = f"A draft ({ctx.pending_action['draft_type']}) is in progress; seller may be answering a field question."
    if ctx.history:
        context += " Last topic: " + ctx.history[-1]["content"][:120]
    try:
        raw = llm.complete(
            system=ROUTER_SYSTEM.format(context=context or "none"),
            messages=[{"role": "user", "content": text}],
            model=config.ROUTER_MODEL,
            max_tokens=120,
        )
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        out = json.loads(raw)
        assert out.get("intent") in ("policy_query", "action_request", "other")
        return out
    except Exception:
        return classify_heuristic(text)


# ---------------------------------------------------------------- main entry

def handle_message(chat_id: str, text: str) -> str:
    st = state_for(chat_id)
    text = text.strip()

    t0 = time.time()

    def _log(reply: str, intent: str, grounded: bool | None = None,
             n_citations: int = 0, event: str | None = None) -> str:
        telemetry.log_turn(
            chat_id, text, reply, intent=intent, language=st.language,
            marketplace=st.marketplace, latency_ms=int((time.time() - t0) * 1000),
            grounded=grounded, n_citations=n_citations, event=event,
        )
        _persist(chat_id, st)
        return reply

    # rate limit (cost guard)
    now = time.time()
    st.msg_timestamps = [t for t in st.msg_timestamps if now - t < 86400]
    if len(st.msg_timestamps) >= config.DAILY_MESSAGE_CAP:
        return _log(RATE_LIMIT_MSG.get(st.language, RATE_LIMIT_MSG["english"]),
                    intent="blocked", event="rate_limit")
    st.msg_timestamps.append(now)

    if text.lower() in ("/start", "start"):
        return _log(INTRO, intent="other", event="start")

    # P0.5 — credential guard runs before anything else
    if any(p.search(text) for p in CREDENTIAL_PATTERNS):
        return _log(CREDENTIAL_WARNING.get(st.language, CREDENTIAL_WARNING["english"]),
                    intent="blocked", event="credential_guard")

    # Scope guard: query about a marketplace we don't cover (deterministic;
    # embeddings can't reliably refuse these — calibration showed overlap)
    tl = text.lower()
    if any(m in tl for m in UNSUPPORTED_MARKETPLACES) and not any(m in tl for m in config.SUPPORTED_MARKETPLACES):
        return _log(UNSUPPORTED_MP_MSG.get(st.language, UNSUPPORTED_MP_MSG["english"]),
                    intent="other", event="unsupported_marketplace")

    cls = classify(text, st)
    st.language = cls.get("language") or st.language
    st.marketplace = cls.get("marketplace") or st.marketplace

    st.history.append({"role": "user", "content": text})
    st.history = st.history[-config.MAX_HISTORY_TURNS * 2:]

    grounded: bool | None = None
    n_citations = 0
    route = cls["intent"]  # the effective route actually taken (logged for metrics)

    # --- the bot just asked for a specific field: this message IS the answer,
    #     no matter what the classifier thinks it looks like
    if st.pending_action and st.awaiting_field:
        pa = st.pending_action
        pa["fields"][st.awaiting_field] = None if text.lower().strip() == "skip" else text
        st.awaiting_field = None
        reply = _continue_action(st, text, already_extracted=True)
        route = "action_request"
    # --- a draft is in progress: treat message as slot answer unless clearly a new topic
    elif st.pending_action and cls["intent"] != "policy_query":
        reply = _continue_action(st, text)
        route = "action_request"
    elif cls["intent"] == "action_request":
        reply = _start_or_continue_action(st, text)
    elif cls["intent"] == "policy_query":
        result = retrieval_agent.answer(
            text, marketplace=st.marketplace, language=st.language,
            history=st.history[:-1][-4:],
        )
        reply = result["answer"]
        grounded = result["found"]
        n_citations = len(result.get("citations", []))
    else:
        reply = OFF_TOPIC.get(st.language, OFF_TOPIC["english"])

    st.history.append({"role": "assistant", "content": reply})
    return _log(reply, intent=route, grounded=grounded, n_citations=n_citations)


# ---------------------------------------------------------------- action flow

def _start_or_continue_action(st: ChatState, text: str) -> str:
    convo = "\n".join(f"{m['role']}: {m['content']}" for m in st.history[-8:])
    ext = action_agent.extract(convo)
    dtype = ext.get("draft_type")
    if not dtype or dtype not in action_agent.DRAFT_TYPES:
        options = "\n".join(f"• {v['label']}" for v in action_agent.DRAFT_TYPES.values())
        if st.language == "hinglish":
            return f"Zaroor! Kaunsa draft chahiye?\n{options}\n\nSaath mein problem ek line mein batao."
        return f"Sure! Which draft do you need?\n{options}\n\nAlso tell me the problem in one line."
    st.pending_action = {
        "draft_type": dtype,
        "marketplace": ext.get("marketplace") or st.marketplace,
        "fields": ext.get("fields", {}),
    }
    return _continue_action(st, text, already_extracted=True)


def _continue_action(st: ChatState, text: str, already_extracted: bool = False) -> str:
    pa = st.pending_action
    if not already_extracted:
        convo = "\n".join(f"{m['role']}: {m['content']}" for m in st.history[-8:])
        ext = action_agent.extract(convo)
        for k, v in (ext.get("fields") or {}).items():
            pa["fields"].setdefault(k, v)
        pa["marketplace"] = pa.get("marketplace") or ext.get("marketplace") or st.marketplace

    missing = action_agent.next_missing_field(pa["draft_type"], pa["fields"])
    if missing:
        st.awaiting_field = missing
        return action_agent.ask_for_field(missing, st.language)

    draft = action_agent.make_draft(pa["draft_type"], pa["marketplace"], pa["fields"], st.language)
    st.pending_action = None
    st.awaiting_field = None
    return draft
