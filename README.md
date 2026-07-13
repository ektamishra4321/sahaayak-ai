# 🛍️ SahaayakAI — AI Support Agent for Indian E-commerce Sellers

!\[Python](https://img.shields.io/badge/python-3.10%2B-blue)
!\[Tests](https://img.shields.io/badge/tests-19%20passing-brightgreen)
!\[License](https://img.shields.io/badge/license-MIT-green)
!\[Status](https://img.shields.io/badge/status-pilot-orange)

**A multi-agent Telegram bot that answers Meesho/Amazon India seller-policy
questions in Hinglish — with citations — and drafts ready-to-submit return
claims, payment-hold emails, and listing appeals.**

Small sellers lose real money to missed claim deadlines, fraudulent returns,
and payment holds — because the answers are buried in dense, English-only
help docs. SahaayakAI compresses "1–2 hours of searching" into one chat message.

```
Seller:  customer ne 15 din baad return kiya, accept karna padega kya?
Bot:     Nahi, zaroori nahi. Customer return window delivery se 7 din ki hoti
         hai... Aap dispute raise kar sakte ho. Chaaho to main draft bana doon?
         📄 Source: Meesho Returns \& Return Claims Policy / Customer Return Window
```

## ✨ Features

* 🔍 **Grounded policy answers (RAG)** — retrieves from indexed official policy
docs and answers *only* from them. Every answer cites its source; if
confidence is low it honestly says "not found" instead of guessing.
* ✍️ **Claim \& email drafting** — slot-filling flow collects order ID, issue,
AWB one question at a time, then generates a copy-paste-ready draft that
quotes the relevant policy. Never emits `\[PLACEHOLDER]` junk.
* 🧠 **Multi-agent architecture** — a cheap/fast model routes intent
(policy question vs. draft request vs. chit-chat); a stronger model composes
answers. Conservative retrieval + productive drafting, cleanly separated.
* 🗣️ **Hinglish-first** — detects and mirrors the seller's language.
* 🛡️ **Safety guardrails** — detects and refuses passwords/OTPs/bank details
before any processing; never auto-submits anything; daily message cap.
* 💾 **Restart-proof** — SQLite persistence: mid-draft conversations survive
redeploys.
* 📊 **Built-in observability** — privacy-safe JSONL telemetry (hashed chat
IDs), a one-command metrics report, groundedness audit sampler, a 50-query
routing eval (96% on the no-LLM fallback alone), and 👍/👎 feedback buttons.

## 🏗️ Architecture

```
Telegram → main.py → ORCHESTRATOR (routing · state · guardrails)
                        ├─→ RETRIEVAL AGENT ──→ ChromaDB (policy corpus)
                        │     answers only from retrieved chunks, cites sources
                        └─→ ACTION AGENT
                              slot-filling → policy-grounded draft
```

|Component|Choice|Why|
|-|-|-|
|Channel|Telegram (long polling)|free token, no webhook/server needed|
|Vector DB|ChromaDB, local embeddings|zero extra API keys, runs anywhere|
|LLM|Anthropic API (2 tiers)|cheap router + quality composer|
|Framework|\~700 lines plain Python|debuggable, no framework magic|
|State|SQLite|pilot-scale persistence, one file|

## 🚀 Quick Start

```bash
git clone <this-repo> \&\& cd seller-support-agent
pip install -r requirements.txt
cp .env.example .env            # add TELEGRAM\_BOT\_TOKEN + ANTHROPIC\_API\_KEY
python -m rag.ingest --reset    # index the policy corpus
python cli.py                   # try it in your terminal
python main.py                  # go live on Telegram
```

Docker: `docker compose up -d --build`. Full runbook in [SETUP.md](SETUP.md). Deep-dive design: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Build it yourself: [docs/BUILD\_GUIDE.md](docs/BUILD_GUIDE.md).

> ⚠️ \*\*Before real sellers use it:\*\* verify every `\[VERIFY]` marker in
> `corpus/` against the live Supplier Panel / Seller Central. The
> no-hallucination guarantee is only as strong as the corpus.

## 🧪 Quality Gates

```bash
pytest tests/ -q                       # 19 tests, no API key needed
python eval/run\_eval.py                # routing accuracy (target >=90%)
python eval/metrics\_report.py --audit  # PRD metrics + groundedness sample
```

## 🗺️ Roadmap

* ✅ v0.1 — RAG core, orchestrator, action agent, Telegram, telemetry, evals
* 🔜 WhatsApp channel (Business API) · screenshot understanding (vision) ·
claim-deadline reminders
* 🔮 More marketplaces (Flipkart) · regional languages (Marathi, Tamil) ·
seller memory

## 📁 Structure

```
agents/        orchestrator, retrieval agent, action agent, telemetry, persistence
rag/           ingestion (chunking) + ChromaDB wrapper
corpus/        marketplace policy docs (markdown, section-structured)
eval/          routing eval set, eval runner, metrics/audit report
tests/         19 pytest tests for the deterministic core
```

## 🤝 Contributing \& Disclaimer

PRs welcome — especially corpus improvements with official sources. This tool
drafts suggestions; sellers must review before submitting. Not affiliated with
Meesho or Amazon. MIT licensed.

