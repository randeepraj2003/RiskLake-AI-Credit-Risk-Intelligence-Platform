"""
RiskLake — API Layer
File   : api/schemas.py

Shared Pydantic schemas used across routers.
Individual routers also define their own response models inline
for self-contained readability.
"""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status:  str
    service: str
    version: str


class ErrorResponse(BaseModel):
    detail:        str
    error_code:    Optional[str] = None
    application_id: Optional[str] = None
