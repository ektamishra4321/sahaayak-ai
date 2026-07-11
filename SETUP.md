# SETUP — from zero to live bot

## Step 1 — Get your two keys (10 minutes)
1. **Telegram token**: open Telegram → search **@BotFather** → send `/newbot` →
   pick a name (e.g. SahaayakAI) and username → copy the token.
2. **Anthropic API key**: https://console.anthropic.com → API Keys → create.
   (Docs: https://docs.claude.com/en/api/overview)

## Step 2 — Configure
```bash
cp .env.example .env     # then paste both keys into .env
```

## Step 3 — Run locally (no Docker)
```bash
pip install -r requirements.txt        # Debian/Ubuntu: add --break-system-packages
python -m rag.ingest --reset           # index the policy corpus (~30s first time)
python cli.py                          # test in terminal first
python main.py                         # go live on Telegram
```
Open your bot on Telegram, send `/start`, then try:
`customer ne 15 din baad return kiya kya karun?`

## Step 3 (alternative) — Run with Docker
```bash
docker compose up -d --build
docker compose logs -f bot
```

## Step 4 — Before real sellers touch it (CRITICAL)
Replace every file in `corpus/` with **verbatim text from official help pages**
(Meesho Supplier Panel help, Amazon Seller Central help). Keep the
`# Title` / `source_url:` / `## Section` structure. Then:
```bash
python -m rag.ingest --reset     # or rebuild the Docker image
```
Every `[VERIFY]` marker still in the corpus = a policy fact you haven't confirmed.

## Step 5 — Daily/weekly ops during the pilot
```bash
python -m pytest tests/ -q             # before every change you ship
python eval/run_eval.py                # routing accuracy (target >=90%)
python eval/metrics_report.py          # PRD metrics from real conversations
python eval/metrics_report.py --audit  # weekly: manually review 30 answers
```
Logs live in `data/logs/conversations.jsonl` (chat IDs hashed; set `LOG_SALT`
in .env for production).

## Step 6 — Recruit 2–3 pilot sellers
Best sources: sellers you know personally > seller Telegram groups > seller
Facebook groups. Offer: "free assistant that answers Meesho/Amazon policy
questions and writes your claim drafts — WhatsApp jaisa hi, Telegram pe."
Ask them to send you a screenshot of one real use in week 1.

## Troubleshooting
- **Bot doesn't reply** → check `TELEGRAM_BOT_TOKEN` in .env; look at console logs.
- **Every answer is "not found"** → corpus not ingested, or `MAX_DISTANCE` too
  low; try raising it in .env (e.g. `MAX_DISTANCE=1.2`).
- **Ungrounded answers slip through** → lower `MAX_DISTANCE`; check the audit.
- **LLM errors** → check `ANTHROPIC_API_KEY` and account credits.
