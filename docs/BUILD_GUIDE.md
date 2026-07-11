# BUILD GUIDE — Making SahaayakAI From Scratch

Nine stages. Each stage is one git commit in this repo, is independently
verifiable, and leaves you with something that runs. Follow the order — it's
chosen so you always test the layer below before building on it.

**Rule of the build:** deterministic guarantees are code; LLMs only get jobs
that need judgment. You'll see this decide where every piece goes.

---

## Stage 1 — Skeleton + Config  *(~30 min)*
**Build:** folder structure (`agents/ rag/ corpus/ eval/ tests/ docs/ data/`),
`config.py`, `requirements.txt`, `.env.example`, `.gitignore`.

**Why first:** every later file imports `config`. Putting all tunables
(model names, `MAX_DISTANCE`, `DAILY_MESSAGE_CAP`) in one place means tuning
never requires touching logic.

**Verify:** `python -c "import config"` runs clean. `git init` and commit —
version control starts at file one, not at the end.

## Stage 2 — Policy Corpus  *(the real work: 1–2 days)*
**Build:** markdown policy docs in `corpus/<marketplace>/`, one topic per
file, structured as `# Title` / `source_url:` / `## Section` headings.

**Why before any code:** the bot's entire value is this content. The
`## Section` structure isn't cosmetic — it's what makes citations point to a
human-checkable location ("Doc / Section").

**How:** read the official Supplier Panel / Seller Central help pages and
write the policies in your own words. Mark anything unconfirmed `[VERIFY]`.
Never trust a secondary blog's number without checking the panel — sources
conflict (we found SAFE-T deadlines differing across current sources).

**Verify:** each file has a title, a source_url, and ≥3 sections.

## Stage 3 — RAG Core  *(half a day)*
**Build:** `rag/store.py` (ChromaDB wrapper; chunk metadata = marketplace,
doc_name, section, source_url) and `rag/ingest.py` (split per-section, then
by ~900 chars with 150 overlap; stable md5 ids so re-ingest upserts).

**Why local embeddings (Chroma default):** zero extra API keys, runs
offline, good enough at this corpus size.

**Verify:** `python -m rag.ingest --reset` reports your chunks; then query
the store directly in a Python shell and confirm the *right section* comes
back for 3–4 test questions before writing any agent.

## Stage 4 — Retrieval Agent  *(half a day)*
**Build:** `agents/llm.py` (the ONE place that calls the LLM API) and
`agents/retrieval_agent.py`.

**The two hallucination brakes go in now, not later:**
1. numeric gate — best distance must be ≤ `MAX_DISTANCE`, else template
   "not found";
2. prompt contract — the model must answer ONLY from the provided chunks
   and output `NO_ANSWER` if they don't answer the question.

**Verify:** ask an in-corpus question → cited answer. Ask about the weather
→ "not found". If either fails, stop and fix before proceeding.

## Stage 5 — Action Agent + Orchestrator + State  *(1–2 days, the hardest stage)*
**Build:** `action_agent.py` (extractor prompt → JSON fields; slot check in
pure code; composer prompt for the final draft), `orchestrator.py`
(Stage-0 gates → state check → router → dispatch), `persistence.py`
(SQLite), `telemetry.py` (JSONL, hashed chat ids).

**The trap everyone hits:** when the bot asks "Order ID kya hai?", the
seller's next message IS the answer — but it often *looks like* a new
question to the classifier. The `awaiting_field` state must override the
router. Build this in from the start; we found it as a live bug.

**Order of gates inside `handle_message`:** rate limit → /start →
credential guard → unsupported-marketplace guard → state check → router.
Safety gates run before any LLM sees the text.

**Verify:** with a mocked `llm.complete`, walk one full draft conversation
in a Python shell: request → field question → answer → complete draft.

## Stage 6 — Channels  *(half a day)*
**Build:** `main.py` (python-telegram-bot, long polling, 👍/👎 feedback
buttons, photo handler → `agents/vision.py` screenshot adapter) and
`cli.py` (terminal chat for keyless-ish local testing).

**Why long polling:** no server, no domain, no webhook — runs from a laptop.
**Verify:** `python cli.py` first, then `python main.py` with real keys and
message your own bot.

## Stage 7 — Evals  *(half a day, pays for itself immediately)*
**Build:** `eval/routing_eval.jsonl` (50 labeled queries — write these
BEFORE tuning the router, they keep you honest), `run_eval.py`,
`retrieval_eval.py` (labeled query → expected section, hit@4 gate ≥90%;
out-of-corpus queries → refusal check), `metrics_report.py`.

**What ours caught:** the retrieval eval exposed that our distance
threshold was an uncalibrated guess — out-of-corpus queries sailed under
it. Measuring distributions showed overlap (no clean threshold exists),
which produced the three-brake design: numeric gate for far garbage,
keyword scope-guard for unsupported marketplaces, NO_ANSWER contract for
the overlap zone. **Run the eval, then calibrate `MAX_DISTANCE` from its
data.**

**Verify:** `python eval/run_eval.py --heuristic` ≥90%;
`python eval/retrieval_eval.py` → PASS.

## Stage 8 — Tests  *(half a day)*
**Build:** `tests/test_core.py` — chunker, heuristic router, credential
guard, rate limit, slot ordering, no-placeholder rule, telemetry privacy,
restart persistence, scope guard. All LLM calls mocked: the suite must run
in seconds with no API key.

**Verify:** `pytest tests/ -q` all green. From now on, run before every
change.

## Stage 9 — Docs + Deploy  *(half a day)*
**Build:** `README.md` (public-facing), `SETUP.md` (zero-to-live runbook),
`docs/ARCHITECTURE.md` (flow first → agent count derived), `LICENSE`,
`Dockerfile` + `docker-compose.yml` (corpus ingested at image build; logs
volume-mounted).

**Verify:** `docker compose up -d --build` and the bot answers on Telegram.

---

## The loop after building
Weekly: `pytest` → `run_eval.py` → `retrieval_eval.py` →
`metrics_report.py --audit` → read logs → expand corpus for real questions
that got "not found" → re-ingest → re-calibrate if the eval says so.
That loop, not the initial build, is what makes it good.
