"""Central configuration. All tunables live here."""
import os
from dotenv import load_dotenv

load_dotenv()

# --- API keys ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# --- Models ---
# Router/classifier: cheap + fast. Answer composition: higher quality.
ROUTER_MODEL = os.getenv("ROUTER_MODEL", "claude-haiku-4-5-20251001")
ANSWER_MODEL = os.getenv("ANSWER_MODEL", "claude-sonnet-4-6")

# --- RAG ---
CHROMA_DIR = os.getenv("CHROMA_DIR", os.path.join(os.path.dirname(__file__), "data", "chroma"))
COLLECTION_NAME = "seller_policies"
CHUNK_SIZE = 900          # chars
CHUNK_OVERLAP = 150       # chars
TOP_K = 4
# Chroma default embeddings return cosine distance; lower = closer.
# If best hit is above this, we say "I couldn't find an official answer".
# CALIBRATED (Jul 2026, eval/retrieval_eval.py): in-corpus top-hit distances
# span 0.44-0.80; out-of-corpus 0.63-0.84. Distributions OVERLAP, so this
# numeric gate only catches clearly-far queries; the NO_ANSWER prompt
# contract in the retrieval agent is the primary hallucination brake for
# the 0.6-0.8 overlap zone. Re-calibrate after any corpus change.
MAX_DISTANCE = float(os.getenv("MAX_DISTANCE", "0.80"))

# --- Behaviour ---
MAX_HISTORY_TURNS = 8      # conversation turns kept per chat for context
DAILY_MESSAGE_CAP = int(os.getenv("DAILY_MESSAGE_CAP", "60"))  # per user, cost guard

SUPPORTED_MARKETPLACES = ["meesho", "amazon"]
