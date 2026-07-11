"""SQLite persistence for per-chat state (fixes the restart-loses-state limitation).

Each ChatState is stored as a JSON blob keyed by chat_id. Cheap and sufficient
for a pilot of a few sellers; swap for Redis/Postgres if this ever scales.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "state.db")
_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.execute("CREATE TABLE IF NOT EXISTS chat_state (chat_id TEXT PRIMARY KEY, state TEXT)")
        _conn.commit()
    return _conn


def save_state(chat_id: str, state_dict: dict) -> None:
    with _lock:
        _db().execute(
            "INSERT INTO chat_state (chat_id, state) VALUES (?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET state = excluded.state",
            (chat_id, json.dumps(state_dict, ensure_ascii=False)),
        )
        _db().commit()


def load_state(chat_id: str) -> dict | None:
    with _lock:
        row = _db().execute("SELECT state FROM chat_state WHERE chat_id = ?", (chat_id,)).fetchone()
    return json.loads(row[0]) if row else None
