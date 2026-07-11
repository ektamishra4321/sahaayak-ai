"""Test suite for the deterministic core (no API key required).

Run:  pytest tests/ -v
LLM calls are monkeypatched; these tests cover routing, guardrails, chunking,
slot-filling and telemetry — the logic most likely to break during refactors.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from agents import action_agent, orchestrator, telemetry
from rag.ingest import _split_text, parse_doc


# ---------------------------------------------------------------- chunker

def test_split_text_respects_size_and_overlap():
    text = ("Sentence one. " * 200).strip()
    parts = _split_text(text, size=300, overlap=50)
    assert all(len(p) <= 300 for p in parts)
    assert len(parts) > 1
    # overlap: consecutive chunks share some content
    assert parts[0][-20:] in text and parts[1][:20] in text


def test_parse_doc_extracts_sections(tmp_path):
    doc = tmp_path / "sample-policy.md"
    doc.write_text("# Test Policy\nsource_url: https://x.y\n\nIntro text.\n\n"
                   "## Section A\nRule one applies.\n\n## Section B\nRule two applies.\n")
    chunks = parse_doc(str(doc), "meesho")
    sections = {c["section"] for c in chunks}
    assert {"Overview", "Section A", "Section B"} <= sections
    assert all(c["marketplace"] == "meesho" for c in chunks)
    assert all(c["source_url"] == "https://x.y" for c in chunks)


# ---------------------------------------------------------------- router (heuristic)

@pytest.mark.parametrize("text,intent", [
    ("return claim ka draft bana do order 123", "action_request"),
    ("payment kab aayega delivery ke baad", "policy_query"),
    ("namaste bhai", "other"),
    ("write an appeal for my suppressed listing", "action_request"),
    ("what is the SAFE-T claim deadline", "policy_query"),
    ("thanks yaar", "other"),
])
def test_heuristic_routing(text, intent):
    assert orchestrator.classify_heuristic(text)["intent"] == intent


def test_language_detection():
    assert orchestrator.classify_heuristic("mera payment hold pe hai")["language"] == "hinglish"
    assert orchestrator.classify_heuristic("my payment is on hold")["language"] == "english"


def test_marketplace_detection():
    assert orchestrator.classify_heuristic("meesho pe return aaya")["marketplace"] == "meesho"
    assert orchestrator.classify_heuristic("amazon listing error")["marketplace"] == "amazon"


# ---------------------------------------------------------------- guardrails

@pytest.mark.parametrize("msg", [
    "mera password: secret123 hai",
    "OTP aya hai 445566",
    "cvv: 123 use karlo",
])
def test_credential_guard_blocks(msg, fresh_chat):
    reply = orchestrator.handle_message(fresh_chat, msg)
    assert "OTP" in reply or "password" in reply.lower()


def test_rate_limit(fresh_chat, monkeypatch):
    monkeypatch.setattr(config, "DAILY_MESSAGE_CAP", 2)
    orchestrator.handle_message(fresh_chat, "/start")
    orchestrator.handle_message(fresh_chat, "/start")
    reply = orchestrator.handle_message(fresh_chat, "hello")
    assert "limit" in reply.lower()


# ---------------------------------------------------------------- slot filling

def test_next_missing_field_order():
    assert action_agent.next_missing_field("return_dispute", {}) == "order_id"
    assert action_agent.next_missing_field("return_dispute", {"order_id": "1"}) == "issue_description"
    assert action_agent.next_missing_field(
        "return_dispute", {"order_id": "1", "issue_description": "used item"}) is None


def test_draft_never_contains_placeholders(monkeypatch):
    monkeypatch.setattr(action_agent, "llm",
                        type("M", (), {"complete": staticmethod(
                            lambda **kw: "Dear team, order 123 ... — Draft by SahaayakAI. Please review details before submitting.")})())
    monkeypatch.setattr(action_agent.retrieval_agent, "answer",
                        lambda **kw: {"found": True, "answer": "policy text", "citations": []})
    draft = action_agent.make_draft("return_dispute", "meesho",
                                    {"order_id": "123", "issue_description": "used"}, "hinglish")
    assert "[ORDER_ID]" not in draft and "Draft by SahaayakAI" in draft


# ---------------------------------------------------------------- telemetry

def test_telemetry_hashes_chat_and_hides_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(telemetry, "LOG_DIR", str(tmp_path))
    monkeypatch.setattr(telemetry, "LOG_FILE", str(tmp_path / "c.jsonl"))
    telemetry.log_turn("12345", "my password: abc", "warned", intent="blocked",
                       language="english", marketplace=None, latency_ms=5,
                       event="credential_guard")
    row = json.loads((tmp_path / "c.jsonl").read_text())
    assert row["chat"] != "12345"          # hashed, never raw
    assert row["text_in"] is None           # credential text never stored
    assert row["event"] == "credential_guard"


# ---------------------------------------------------------------- fixtures

@pytest.fixture
def fresh_chat():
    """Unique chat id per test so ChatState doesn't leak between tests."""
    import uuid
    return f"test-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------- slot-answer routing (regression)

def test_slot_answer_completes_draft_even_if_it_looks_like_policy(fresh_chat, monkeypatch):
    """Bug found in simulation: seller's answer to a slot question was mis-routed
    to policy retrieval because it *looked* like a policy query. awaiting_field
    must override the classifier."""
    import json as j
    from agents import llm as llm_mod, retrieval_agent

    def fake(system, messages, model, max_tokens=1024):
        if "Classify" in system:
            return j.dumps({"intent": "policy_query", "language": "hinglish", "marketplace": "meesho"})
        if "Extract structured fields" in system:
            return j.dumps({"draft_type": "return_dispute", "marketplace": "meesho",
                            "fields": {"order_id": "MSH123"}})
        return "Full draft here — Draft by SahaayakAI. Please review details before submitting."

    monkeypatch.setattr(llm_mod, "complete", fake)
    monkeypatch.setattr(retrieval_agent, "answer",
                        lambda **kw: {"found": True, "answer": "policy", "citations": []})

    st = orchestrator.state_for(fresh_chat)
    st.pending_action = {"draft_type": "return_dispute", "marketplace": "meesho",
                         "fields": {"order_id": "MSH123"}}
    st.awaiting_field = "issue_description"

    reply = orchestrator.handle_message(fresh_chat, "customer ne used kurta bheja wapas")
    assert "Draft by SahaayakAI" in reply          # draft completed, not policy answer
    assert st.pending_action is None                # state cleaned up


# ---------------------------------------------------------------- persistence

def test_state_survives_restart(fresh_chat, tmp_path, monkeypatch):
    from agents import persistence
    monkeypatch.setattr(persistence, "DB_PATH", str(tmp_path / "s.db"))
    monkeypatch.setattr(persistence, "_conn", None)
    st = orchestrator.state_for(fresh_chat)
    st.pending_action = {"draft_type": "return_dispute", "marketplace": "meesho",
                         "fields": {"order_id": "X1"}}
    st.awaiting_field = "issue_description"
    orchestrator._persist(fresh_chat, st)
    orchestrator._chats.clear()                      # simulated restart
    st2 = orchestrator.state_for(fresh_chat)
    assert st2.pending_action["fields"]["order_id"] == "X1"
    assert st2.awaiting_field == "issue_description"


# ---------------------------------------------------------------- scope guard

def test_unsupported_marketplace_guard(fresh_chat):
    reply = orchestrator.handle_message(fresh_chat, "flipkart pe seller account kaise banate hain")
    assert "Meesho" in reply and "Amazon" in reply     # polite scope redirect

def test_supported_marketplace_not_blocked_when_both_mentioned(fresh_chat, monkeypatch):
    # "flipkart se meesho pe shift" mentions both -> must NOT be scope-blocked
    from agents import llm as llm_mod, retrieval_agent
    monkeypatch.setattr(llm_mod, "complete", lambda **kw: '{"intent":"policy_query","language":"hinglish","marketplace":"meesho"}')
    monkeypatch.setattr(retrieval_agent, "answer", lambda *a, **kw: {"found": True, "answer": "ok. Source: X", "citations": [{}]})
    reply = orchestrator.handle_message(fresh_chat, "flipkart chhod ke meesho pe aaya hoon, return policy kya hai")
    assert "Source" in reply
