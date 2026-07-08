"""
RiskLake — Gold Layer
Module : ml/inference.py

Loaded once at FastAPI startup. Provides two public functions:

    predict(application_id)  → PD probability + risk grade + ensemble scores
    explain(application_id)  → SHAP-based ranked risk drivers (from PostgreSQL)

Both functions are called by:
    api/routers/risk.py     (/predict, /explain endpoints)
    rag/query_engine.py     (injects SHAP context into the credit analyst prompt)
"""

from __future__ import annotations

import json
import logging
import os
import pickle
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg2

log = logging.getLogger("risklake.inference")

PROJECT_ROOT = Path(os.environ.get("RISKLAKE_ROOT", Path(__file__).resolve().parents[1]))
MODELS_DIR   = PROJECT_ROOT / "ml" / "models"

PG_CONN = {
    "host":     os.environ.get("PG_HOST",     "localhost"),
    "port":     int(os.environ.get("PG_PORT", "5432")),
    "dbname":   os.environ.get("PG_DB",       "risklake"),
    "user":     os.environ.get("PG_USER",     "risklake"),
    "password": os.environ.get("PG_PASSWORD"),
}

# ── Load artefacts once at import time ───────────────────────────────────────

def _load_artefacts():
    rf_path   = MODELS_DIR / "rf_pd_model.pkl"
    lr_path   = MODELS_DIR / "lr_pd_model.pkl"
    feat_path = MODELS_DIR / "feature_columns.json"
    meta_path = MODELS_DIR / "model_metadata.json"

    if not rf_path.exists():
        raise FileNotFoundError(
            f"Model not found at {rf_path}. "
            "Run ml/train_pd_model.py first."
        )

    with open(rf_path,   "rb") as f: rf = pickle.load(f)
    with open(lr_path,   "rb") as f: lr = pickle.load(f)
    with open(feat_path)       as f: feature_cols = json.load(f)
    with open(meta_path)       as f: metadata     = json.load(f)

    log.info(
        "Models loaded: version=%s | AUC=%.4f | features=%d",
        metadata.get("model_version"), metadata.get("ensemble_auc"), len(feature_cols),
    )
    return rf, lr, feature_cols, metadata


try:
    _RF, _LR, _FEATURE_COLS, _METADATA = _load_artefacts()
except FileNotFoundError:
    log.warning("Models not yet trained — inference will fail until train_pd_model.py is run.")
    _RF = _LR = _FEATURE_COLS = _METADATA = None


# ── Public API ────────────────────────────────────────────────────────────────

def predict(application_id: str) -> dict[str, Any]:
    """
    Fetch pre-computed PD scores from gold.pd_predictions.

    If the application hasn't been scored yet (new application), falls back
    to live inference by fetching the feature row from Silver tables.

    Returns
    -------
    {
        "application_id":     "APP000042",
        "customer_id":        "CUST00099",
        "pd_probability_ens": 0.312,
        "pd_probability_rf":  0.294,
        "pd_probability_lr":  0.355,
        "pd_prediction":      0,
        "risk_grade":         "C",
        "model_version":      "v20240601_0100",
        "source":             "cache"   # or "live_inference"
    }
    """
    conn = psycopg2.connect(**PG_CONN)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT application_id, customer_id,
                       pd_probability_rf, pd_probability_lr, pd_probability_ens,
                       pd_prediction, risk_grade, model_version
                FROM   gold.pd_predictions
                WHERE  application_id = %s
                ORDER  BY scored_at DESC
                LIMIT  1
                """,
                (application_id,),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if row:
        cols = ["application_id", "customer_id", "pd_probability_rf",
                "pd_probability_lr", "pd_probability_ens",
                "pd_prediction", "risk_grade", "model_version"]
        return {**dict(zip(cols, row)), "source": "cache"}

    # Fallback: live inference from Silver feature tables
    log.warning("application_id=%s not in gold.pd_predictions — running live inference", application_id)
    return _live_predict(application_id)


def explain(application_id: str, top_n: int = 5) -> dict[str, Any]:
    """
    Return the top-N SHAP risk drivers for an application.

    Used by:
      - FastAPI GET /explain/{application_id}
      - RAG query_engine to build the credit analyst context string

    Returns
    -------
    {
        "application_id": "APP000042",
        "model_version":  "v20240601_0100",
        "risk_drivers": [
            {"rank": 1, "feature": "dti_ratio",           "shap_value": 0.18, "direction": "increases_risk"},
            {"rank": 2, "feature": "credit_stress_score", "shap_value": 0.12, "direction": "increases_risk"},
            {"rank": 3, "feature": "emi_regularity_score","shap_value":-0.09, "direction": "decreases_risk"},
        ]
    }
    """
    conn = psycopg2.connect(**PG_CONN)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT feature_name, shap_value, direction, rank, model_version
                FROM   gold.shap_values
                WHERE  application_id = %s
                ORDER  BY rank ASC
                LIMIT  %s
                """,
                (application_id, top_n),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return {
            "application_id": application_id,
            "model_version":  None,
            "risk_drivers":   [],
            "note": "No SHAP values found. Run train_pd_model.py to generate explanations.",
        }

    model_version = rows[0][4]
    return {
        "application_id": application_id,
        "model_version":  model_version,
        "risk_drivers": [
            {
                "rank":        r[3],
                "feature":     r[0],
                "shap_value":  r[1],
                "direction":   r[2],
            }
            for r in rows
        ],
    }


def build_shap_context_string(application_id: str) -> str:
    """
    Returns a plain-English summary of SHAP drivers for injection into
    the RAG credit analyst system prompt.

    Example output:
      "Top risk drivers for APP000042:
         1. dti_ratio = 0.18 → INCREASES default risk
         2. credit_stress_score = 0.12 → INCREASES default risk
         3. emi_regularity_score = -0.09 → DECREASES default risk (protective factor)"
    """
    explanation = explain(application_id, top_n=5)
    drivers     = explanation.get("risk_drivers", [])

    if not drivers:
        return f"No SHAP explanation available for application {application_id}."

    lines = [f"Top risk drivers for {application_id}:"]
    for d in drivers:
        direction_str = "INCREASES default risk" if d["direction"] == "increases_risk" \
                        else "DECREASES default risk (protective factor)"
        lines.append(
            f"  {d['rank']}. {d['feature']} (SHAP={d['shap_value']:+.4f}) → {direction_str}"
        )
    return "\n".join(lines)


# ── Live inference fallback ───────────────────────────────────────────────────

def _live_predict(application_id: str) -> dict[str, Any]:
    """
    Fetch the feature row from Silver and score it in real-time.
    Used for applications that arrive after the last nightly model refresh.
    """
    if _RF is None:
        raise RuntimeError("Models not loaded. Cannot perform live inference.")

    conn = psycopg2.connect(**PG_CONN)
    try:
        query = """
            SELECT d.*, COALESCE(u.bureau_utilisation_pct, 0) AS bureau_utilisation_pct,
                   COALESCE(u.avg_monthly_spend_inr,   0) AS avg_monthly_spend_inr,
                   COALESCE(u.spend_volatility_inr,    0) AS spend_volatility_inr,
                   COALESCE(u.emi_payment_count_12m,   0) AS emi_payment_count_12m,
                   COALESCE(u.emi_regularity_score,    0) AS emi_regularity_score,
                   COALESCE(u.credit_stress_score,     0) AS credit_stress_score,
                   COALESCE(u.flagged_txn_rate,        0) AS flagged_txn_rate,
                   COALESCE(u.total_txns_12m,          0) AS total_txns_12m,
                   COALESCE(u.utilisation_band,   'unknown') AS utilisation_band,
                   COALESCE(u.credit_age_band,    'unknown') AS credit_age_band
            FROM silver_silver.feat_dti_ratio d
            LEFT JOIN silver_silver.feat_credit_util u USING (customer_id)
            WHERE d.application_id = %s
        """
        df = pd.read_sql(query, conn, params=(application_id,))
    finally:
        conn.close()

    if df.empty:
        raise ValueError(f"application_id={application_id} not found in Silver tables.")

    from app.services.train_pd_model import engineer_features, pd_to_risk_grade
    df_enc, _ = engineer_features(df.copy())

    # Align columns to training feature set
    X = df_enc.reindex(columns=_FEATURE_COLS, fill_value=0)

    rf_prob  = float(_RF.predict_proba(X)[0, 1])
    lr_prob  = float(_LR.predict_proba(X)[0, 1])
    ens_prob = 0.70 * rf_prob + 0.30 * lr_prob

    return {
        "application_id":     application_id,
        "customer_id":        str(df.iloc[0]["customer_id"]),
        "pd_probability_rf":  round(rf_prob, 6),
        "pd_probability_lr":  round(lr_prob, 6),
        "pd_probability_ens": round(ens_prob, 6),
        "pd_prediction":      int(ens_prob >= 0.5),
        "risk_grade":         pd_to_risk_grade(ens_prob),
        "model_version":      _METADATA.get("model_version", "unknown"),
        "source":             "live_inference",
    }
