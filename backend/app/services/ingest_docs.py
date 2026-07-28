"""
RiskLake — RAG Layer
Script : rag/ingest_docs.py

Chunks lending policy documents, embeds with sentence-transformers,
and upserts into a persistent ChromaDB collection.

Sources: rag/docs/*.txt  (RBI policy, Basel III, AML typologies, product guidelines)
Usage  : python rag/ingest_docs.py [--reset]

Author : Randeep Raj
Project: RiskLake
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import sys
from collections.abc import Iterator
from pathlib import Path

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

PROJECT_ROOT    = Path(os.environ.get("RISKLAKE_ROOT", Path(__file__).resolve().parents[1]))
DOCS_DIR        = PROJECT_ROOT / "rag" / "docs"
CHROMA_DIR      = PROJECT_ROOT / "rag" / "chroma_db"
COLLECTION_NAME = "risklake_policies"
EMBED_MODEL     = "all-MiniLM-L6-v2"
MAX_CHUNK_CHARS = 800

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("risklake.ingest")


# ── Chunking ─────────────────────────────────────────────────────────────────

def _chunk_id(source: str, idx: int, text: str) -> str:
    return hashlib.sha256(f"{source}::{idx}::{text[:50]}".encode()).hexdigest()[:16]


def _extract_section(text: str) -> str:
    match = re.search(r"SECTION\s+\d+[:\s]+([^\n]+)", text)
    return match.group(1).strip().lower() if match else "general"


def _split_into_chunks(text: str) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    for para in paragraphs:
        if len(para) <= MAX_CHUNK_CHARS:
            chunks.append(para)
        else:
            sub     = [s.strip() for s in para.split("\n") if s.strip()]
            current = ""
            for line in sub:
                if len(current) + len(line) + 1 <= MAX_CHUNK_CHARS:
                    current = (current + "\n" + line).strip()
                else:
                    if current:
                        chunks.append(current)
                    current = line
            if current:
                chunks.append(current)
    return [c for c in chunks if len(c) > 30]


def iter_documents(docs_dir: Path) -> Iterator[dict]:
    for doc_path in sorted(docs_dir.glob("*.txt")):
        source = doc_path.stem
        chunks = _split_into_chunks(doc_path.read_text(encoding="utf-8"))
        log.info("  %s -> %d chunks", doc_path.name, len(chunks))
        for idx, chunk_text in enumerate(chunks):
            yield {
                "id":   _chunk_id(source, idx, chunk_text),
                "text": chunk_text,
                "metadata": {
                    "source":       source,
                    "filename":     doc_path.name,
                    "section":      _extract_section(chunk_text),
                    "chunk_index":  idx,
                    "char_count":   len(chunk_text),
                    "total_chunks": len(chunks),
                },
            }


# ── ChromaDB ──────────────────────────────────────────────────────────────────

def get_chroma_collection(reset: bool = False) -> chromadb.Collection:
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(
        path=str(CHROMA_DIR),
        settings=Settings(anonymized_telemetry=False),
    )
    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
            log.info("Deleted existing collection '%s'.", COLLECTION_NAME)
        except Exception:
            pass
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    log.info("Collection '%s' ready. Current size: %d", COLLECTION_NAME, collection.count())
    return collection


# ── Main ingestion ────────────────────────────────────────────────────────────

def ingest(docs_dir: Path, reset: bool = False) -> int:
    log.info("=" * 56)
    log.info("RiskLake RAG — Document Ingestion")
    log.info("Source:   %s", docs_dir)
    log.info("ChromaDB: %s", CHROMA_DIR)
    log.info("=" * 56)

    all_docs = list(iter_documents(docs_dir))
    if not all_docs:
        log.error("No chunks produced. Run generate_docs.py first.")
        return 0

    log.info("Total chunks: %d. Loading embedding model...", len(all_docs))
    model = SentenceTransformer(EMBED_MODEL)

    texts      = [d["text"] for d in all_docs]
    embeddings = model.encode(texts, batch_size=64, show_progress_bar=True,
                              normalize_embeddings=True).tolist()

    collection = get_chroma_collection(reset=reset)

    for i in range(0, len(all_docs), 100):
        batch = all_docs[i:i + 100]
        collection.upsert(
            ids        = [d["id"]       for d in batch],
            documents  = [d["text"]     for d in batch],
            embeddings = embeddings[i:i + 100],
            metadatas  = [d["metadata"] for d in batch],
        )
        log.info("  Upserted %d / %d", min(i + 100, len(all_docs)), len(all_docs))

    log.info("Ingestion complete. Collection size: %d", collection.count())
    return len(all_docs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset",    action="store_true")
    parser.add_argument("--docs-dir", default=str(DOCS_DIR))
    args  = parser.parse_args()
    count = ingest(Path(args.docs_dir), reset=args.reset)
    if count == 0:
        sys.exit(1)
    print(f"\nDone. {count} chunks ingested into ChromaDB.")
