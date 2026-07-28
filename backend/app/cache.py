"""
RiskLake — API Layer
Module : api/cache.py

Thin Redis wrapper used by FastAPI routers.
TTL strategy:
  - PD predictions  : 1 hour  (scores refresh nightly via Airflow)
  - SHAP explanations: 1 hour
  - Portfolio KPIs  : 5 minutes (aggregates change more frequently)

Falls back gracefully if Redis is unavailable — the API still works,
just without caching. This prevents Redis becoming a hard dependency
in dev environments.

Author : Randeep Raj
Project: RiskLake
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import redis

log = logging.getLogger("risklake.cache")

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_DB   = int(os.environ.get("REDIS_DB",   "0"))

TTL_PREDICT   = 3600   # 1 hour
TTL_EXPLAIN   = 3600   # 1 hour
TTL_PORTFOLIO = 300    # 5 minutes

# Attempt connection at import time; failures are non-fatal
try:
    _redis_client = redis.Redis(
        host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB,
        socket_connect_timeout=2, decode_responses=True,
    )
    _redis_client.ping()
    log.info("Redis connected at %s:%d", REDIS_HOST, REDIS_PORT)
except Exception as exc:
    log.warning("Redis unavailable (%s) — caching disabled.", exc)
    _redis_client = None


def cache_get(key: str) -> Any | None:
    """Return cached value (deserialized from JSON) or None on miss/error."""
    if _redis_client is None:
        return None
    try:
        raw = _redis_client.get(key)
        return json.loads(raw) if raw else None
    except Exception as exc:
        log.warning("Cache GET error for key=%s: %s", key, exc)
        return None


def cache_set(key: str, value: Any, ttl: int = TTL_PREDICT) -> None:
    """Serialize value to JSON and store with TTL. Silent on error."""
    if _redis_client is None:
        return
    try:
        _redis_client.setex(key, ttl, json.dumps(value))
    except Exception as exc:
        log.warning("Cache SET error for key=%s: %s", key, exc)


def cache_delete(key: str) -> None:
    if _redis_client is None:
        return
    try:
        _redis_client.delete(key)
    except Exception as exc:
        log.warning("Cache DELETE error for key=%s: %s", key, exc)


def make_predict_key(application_id: str) -> str:
    return f"risklake:predict:{application_id}"


def make_explain_key(application_id: str, top_n: int) -> str:
    return f"risklake:explain:{application_id}:top{top_n}"


def make_portfolio_key() -> str:
    return "risklake:portfolio:summary"
