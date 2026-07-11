"""Ingest policy docs from corpus/<marketplace>/*.md into the vector store.

Doc format convention (markdown):
  - First line: `# <Doc Name>`
  - Optional line anywhere near top: `source_url: https://...`
  - `## <Section>` headers define citation sections.

Chunks are split per-section, then by size with overlap, so a citation can always
point to "<Doc Name>, <Section>".

Run:  python -m rag.ingest [--reset]
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from rag.store import PolicyStore

CORPUS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "corpus")


def _split_text(text: str, size: int, overlap: int) -> list[str]:
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []
    parts, start = [], 0
    while start < len(text):
        end = start + size
        # try to break at a sentence/newline boundary
        if end < len(text):
            window = text[start:end]
            cut = max(window.rfind("\n"), window.rfind(". "))
            if cut > size * 0.5:
                end = start + cut + 1
        parts.append(text[start:end].strip())
        start = max(end - overlap, start + 1)
        if start >= len(text):
            break
    return [p for p in parts if p]


def parse_doc(path: str, marketplace: str) -> list[dict]:
    raw = open(path, encoding="utf-8").read()
    doc_name = os.path.splitext(os.path.basename(path))[0].replace("-", " ").title()
    m = re.search(r"^#\s+(.+)$", raw, re.M)
    if m:
        doc_name = m.group(1).strip()
    src = re.search(r"^source_url:\s*(\S+)", raw, re.M)
    source_url = src.group(1) if src else ""

    # split into sections on '## '
    sections = re.split(r"^##\s+", raw, flags=re.M)
    chunks: list[dict] = []
    for i, sec in enumerate(sections):
        if i == 0:
            section_name, body = "Overview", re.sub(r"^#\s+.+$", "", sec, flags=re.M)
            body = re.sub(r"^source_url:.*$", "", body, flags=re.M)
        else:
            lines = sec.split("\n", 1)
            section_name = lines[0].strip()
            body = lines[1] if len(lines) > 1 else ""
        for j, piece in enumerate(_split_text(body, config.CHUNK_SIZE, config.CHUNK_OVERLAP)):
            uid = hashlib.md5(f"{marketplace}|{doc_name}|{section_name}|{j}|{piece[:40]}".encode()).hexdigest()
            chunks.append(
                {
                    "id": uid,
                    "text": f"[{marketplace.upper()} — {doc_name} / {section_name}]\n{piece}",
                    "marketplace": marketplace,
                    "doc_name": doc_name,
                    "section": section_name,
                    "source_url": source_url,
                }
            )
    return chunks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="wipe the collection first")
    args = ap.parse_args()

    store = PolicyStore()
    if args.reset:
        store.reset()

    total = 0
    for marketplace in config.SUPPORTED_MARKETPLACES:
        mdir = os.path.join(CORPUS_DIR, marketplace)
        if not os.path.isdir(mdir):
            continue
        for fname in sorted(os.listdir(mdir)):
            if not fname.endswith(".md"):
                continue
            chunks = parse_doc(os.path.join(mdir, fname), marketplace)
            store.add_chunks(chunks)
            total += len(chunks)
            print(f"  ingested {marketplace}/{fname}: {len(chunks)} chunks")
    print(f"Done. Collection now holds {store.count()} chunks (added/updated {total}).")


if __name__ == "__main__":
    main()
