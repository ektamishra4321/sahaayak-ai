"""Thin wrapper around ChromaDB so the rest of the app never touches chroma directly.

Uses Chroma's default embedding function (local ONNX MiniLM — no extra API key).
Every chunk is stored with metadata: {marketplace, doc_name, section, source_url}.
"""
from __future__ import annotations

import chromadb

import config


class PolicyStore:
    def __init__(self, persist_dir: str = config.CHROMA_DIR):
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._col = self._client.get_or_create_collection(
            name=config.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    # ---------- write ----------
    def add_chunks(self, chunks: list[dict]) -> None:
        """chunks: [{id, text, marketplace, doc_name, section, source_url}]"""
        if not chunks:
            return
        self._col.upsert(
            ids=[c["id"] for c in chunks],
            documents=[c["text"] for c in chunks],
            metadatas=[
                {
                    "marketplace": c["marketplace"],
                    "doc_name": c["doc_name"],
                    "section": c.get("section", ""),
                    "source_url": c.get("source_url", ""),
                }
                for c in chunks
            ],
        )

    def count(self) -> int:
        return self._col.count()

    def reset(self) -> None:
        self._client.delete_collection(config.COLLECTION_NAME)
        self._col = self._client.get_or_create_collection(
            name=config.COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
        )

    # ---------- read ----------
    def query(
        self, text: str, marketplace: str | None = None, top_k: int = config.TOP_K
    ) -> list[dict]:
        """Returns [{text, marketplace, doc_name, section, source_url, distance}] sorted by distance."""
        where = {"marketplace": marketplace} if marketplace in config.SUPPORTED_MARKETPLACES else None
        res = self._col.query(query_texts=[text], n_results=top_k, where=where)
        out = []
        for doc, meta, dist in zip(
            res["documents"][0], res["metadatas"][0], res["distances"][0]
        ):
            out.append({"text": doc, "distance": dist, **meta})
        return out
