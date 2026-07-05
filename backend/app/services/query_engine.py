"""
RiskLake — RAG Layer
Module : rag/query_engine.py
Updated to use Groq (llama-3.1-8b-instant) instead of Gemini.
Author : Randeep Raj
"""

from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import chromadb
from groq import Groq
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

PROJECT_ROOT    = Path(os.environ.get("RISKLAKE_ROOT", Path(__file__).resolve().parents[1]))
CHROMA_DIR = Path(__file__).resolve().parents[1] / "rag" / "chroma_db"
COLLECTION_NAME = "risklake_policies"
EMBED_MODEL     = "all-MiniLM-L6-v2"
GROQ_MODEL      = "llama-3.1-8b-instant"
TOP_K           = 5
MAX_TOKENS      = 1024
GROQ_API_KEY    = os.environ.get("GROQ_API_KEY", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("risklake.query_engine")


@dataclass
class CitedSource:
    source:      str
    filename:    str
    section:     str
    chunk_index: int
    excerpt:     str
    distance:    float


@dataclass
class CreditAnalystResponse:
    question:       str
    answer:         str
    sources:        list[CitedSource] = field(default_factory=list)
    application_id: str | None        = None
    pd_context:     dict | None       = None
    shap_context:   dict | None       = None
    model_used:     str               = GROQ_MODEL
    retrieval_ms:   float             = 0.0
    generation_ms:  float             = 0.0
    tokens_used:    int               = 0


_embed_model: SentenceTransformer | None = None
_chroma_coll: chromadb.Collection  | None = None


def _get_embed_model() -> SentenceTransformer:
    global _embed_model
    if _embed_model is None:
        log.info("Loading embedding model: %s", EMBED_MODEL)
        _embed_model = SentenceTransformer(EMBED_MODEL)
    return _embed_model


def _get_collection() -> chromadb.Collection:
    global _chroma_coll
    if _chroma_coll is None:
        client       = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False)
        )
        _chroma_coll = client.get_collection(COLLECTION_NAME)
        log.info("ChromaDB loaded: %d documents", _chroma_coll.count())
    return _chroma_coll


def retrieve(question: str, top_k: int = TOP_K) -> tuple[list[CitedSource], str]:
    model      = _get_embed_model()
    collection = _get_collection()
    q_emb      = model.encode(question, normalize_embeddings=True).tolist()

    results   = collection.query(
        query_embeddings=[q_emb], n_results=top_k,
        include=["documents", "metadatas", "distances"]
    )
    docs      = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    sources: list[CitedSource] = []
    context_blocks: list[str] = []

    for i, (doc, meta, dist) in enumerate(zip(docs, metadatas, distances)):
        sources.append(CitedSource(
            source=meta.get("source", "unknown"),
            filename=meta.get("filename", ""),
            section=meta.get("section", "general"),
            chunk_index=meta.get("chunk_index", i),
            excerpt=doc[:200],
            distance=round(float(dist), 4),
        ))
        context_blocks.append(
            f"[Source {i+1}: {meta.get('source','policy')} — {meta.get('section','general')}]\n{doc}"
        )

    log.info("Retrieved %d chunks. Best distance: %.4f", len(sources), distances[0])
    return sources, "\n\n---\n\n".join(context_blocks)


def build_prompt(question: str, policy_context: str,
                 pd_context: dict | None = None,
                 shap_context: str | None = None) -> str:

    system = """You are the RiskLake AI Credit Analyst — an expert in retail credit risk,
Indian banking regulations (RBI), Basel III, and loan underwriting.

Rules:
1. Ground every answer in the policy context provided. Cite [Source N].
2. Reference the customer's PD probability and SHAP drivers if provided.
3. Use professional language suitable for a credit officer.
4. If context is insufficient, say so — never fabricate regulatory thresholds.
5. Structure: (a) direct answer, (b) policy basis with citations, (c) recommendation."""

    policy_block = f"RELEVANT POLICY CONTEXT:\n\n{policy_context}"

    customer_block = ""
    if pd_context:
        customer_block = (
            f"\nCUSTOMER RISK PROFILE:\n"
            f"  Application ID : {pd_context.get('application_id','N/A')}\n"
            f"  Customer ID    : {pd_context.get('customer_id','N/A')}\n"
            f"  PD Probability : {pd_context.get('pd_probability_ens',0):.2%}\n"
            f"  Risk Grade     : {pd_context.get('risk_grade','N/A')}  (A=lowest, E=highest)\n"
            f"  Model Version  : {pd_context.get('model_version','N/A')}"
        )

    shap_block = f"\nSHAP RISK DRIVERS:\n{shap_context}" if shap_context else ""

    question_block = (
        f"\nCREDIT ANALYST QUESTION:\n{question}\n\n"
        "Provide a thorough, policy-grounded answer with source citations."
    )

    return "\n\n".join(filter(None, [system, policy_block, customer_block, shap_block, question_block]))


def generate(prompt: str, stream: bool = False) -> tuple[str, int]:
    if not GROQ_API_KEY:
        raise EnvironmentError("GROQ_API_KEY not set. export GROQ_API_KEY=your_key")
    client = Groq(api_key=GROQ_API_KEY)
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=MAX_TOKENS,
        temperature=0.2,
    )
    answer = response.choices[0].message.content
    tokens = response.usage.total_tokens
    return answer, tokens


def query(question: str, application_id: str | None = None,
          top_k: int = TOP_K, stream: bool = False) -> CreditAnalystResponse:
    log.info("Query: '%s...' | app_id=%s", question[:60], application_id)

    t0 = time.perf_counter()
    sources, policy_ctx = retrieve(question, top_k=top_k)
    retrieval_ms = (time.perf_counter() - t0) * 1000

    pd_ctx: dict | None = None
    shap_str: str | None = None
    shap_dict: dict | None = None

    if application_id:
        try:
            import psycopg2
            conn = psycopg2.connect(
                host=os.environ.get("PG_HOST","localhost"),
                dbname=os.environ.get("PG_DB","risklake"),
                user=os.environ.get("PG_USER","postgres"),
                password=os.environ.get("PG_PASSWORD","risklake")
            )
            cur = conn.cursor()
            cur.execute("""
                SELECT application_id, customer_id, pd_probability_ens, risk_grade, model_version
                FROM gold.pd_predictions WHERE application_id = %s
                ORDER BY scored_at DESC LIMIT 1
            """, (application_id.upper(),))
            row = cur.fetchone()
            if row:
                pd_ctx = {
                    "application_id": row[0], "customer_id": row[1],
                    "pd_probability_ens": float(row[2]), "risk_grade": row[3],
                    "model_version": row[4]
                }
                cur.execute("""
                    SELECT feature_name, shap_value, direction, rank
                    FROM gold.shap_values WHERE application_id = %s
                    ORDER BY rank LIMIT 5
                """, (application_id.upper(),))
                shap_rows = cur.fetchall()
                if shap_rows:
                    shap_str = f"Top risk drivers for {application_id}:\n"
                    for r in shap_rows:
                        direction = "INCREASES risk" if r[2] == "increases_risk" else "DECREASES risk"
                        shap_str += f"  {r[3]}. {r[0]} (SHAP={r[1]:+.4f}) → {direction}\n"
                    shap_dict = {"application_id": application_id, "risk_drivers": [
                        {"rank": r[3], "feature": r[0], "shap_value": float(r[1]), "direction": r[2]}
                        for r in shap_rows
                    ]}
            conn.close()
        except Exception as exc:
            log.warning("Could not load customer context: %s", exc)

    prompt = build_prompt(question, policy_ctx, pd_ctx, shap_str)

    t1 = time.perf_counter()
    answer, tokens = generate(prompt, stream=stream)
    generation_ms = (time.perf_counter() - t1) * 1000

    log.info("Done | retrieval=%.0fms | generation=%.0fms | tokens=%d",
             retrieval_ms, generation_ms, tokens)

    return CreditAnalystResponse(
        question=question, answer=answer, sources=sources,
        application_id=application_id, pd_context=pd_ctx, shap_context=shap_dict,
        retrieval_ms=round(retrieval_ms, 1), generation_ms=round(generation_ms, 1),
        tokens_used=tokens,
    )


def explain_application(application_id: str) -> CreditAnalystResponse:
    return query(
        question=(
            f"Provide a complete credit risk assessment for application {application_id}. "
            "Explain the key risk factors, cite relevant policy thresholds, "
            "and give a clear approve/decline recommendation with rationale."
        ),
        application_id=application_id,
    )
