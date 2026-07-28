"""
RiskLake — API Layer
Router : api/routers/analyst.py

Endpoints
---------
POST /analyst/ask
    Body: { "question": "...", "application_id": "APP000042" (optional) }
    Returns: CreditAnalystResponse as JSON

POST /analyst/explain/{application_id}
    Returns: Full credit narrative for one application

GET  /analyst/health
    Returns: ChromaDB doc count + model status
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "rag"))
from app.services.query_engine import (
    CreditAnalystResponse,
    _get_collection,
    explain_application,
    query,
)

router = APIRouter(prefix="/analyst", tags=["AI Credit Analyst"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class AskRequest(BaseModel):
    question:       str
    application_id: str | None = None
    top_k:          int           = 5


class SourceOut(BaseModel):
    source:   str
    section:  str
    excerpt:  str
    distance: float


class AskResponse(BaseModel):
    question:       str
    answer:         str
    sources:        list[SourceOut]
    application_id: str | None
    pd_context:     dict | None
    shap_context:   dict | None
    retrieval_ms:   float
    generation_ms:  float
    tokens_used:    int


def _to_response(r: CreditAnalystResponse) -> AskResponse:
    return AskResponse(
        question       = r.question,
        answer         = r.answer,
        sources        = [SourceOut(source=s.source, section=s.section,
                                    excerpt=s.excerpt, distance=s.distance)
                          for s in r.sources],
        application_id = r.application_id,
        pd_context     = r.pd_context,
        shap_context   = r.shap_context,
        retrieval_ms   = r.retrieval_ms,
        generation_ms  = r.generation_ms,
        tokens_used    = r.tokens_used,
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest) -> AskResponse:
    """Ask the AI credit analyst any question, optionally scoped to one application."""
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="Question cannot be empty.")
    try:
        result = query(req.question, application_id=req.application_id, top_k=req.top_k)
        return _to_response(result)
    except OSError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analyst error: {e}")


@router.post("/explain/{application_id}", response_model=AskResponse)
async def explain(application_id: str) -> AskResponse:
    """Generate a full credit risk narrative for a specific application."""
    try:
        result = explain_application(application_id)
        return _to_response(result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Explanation error: {e}")


@router.get("/health")
async def health() -> dict:
    """Check ChromaDB collection status and document count."""
    try:
        coll = _get_collection()
        return {"status": "ok", "collection": coll.name, "doc_count": coll.count()}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
