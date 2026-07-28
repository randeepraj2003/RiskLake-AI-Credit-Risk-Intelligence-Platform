"""
RiskLake - Model Monitoring & Drift Detection
File: backend/app/services/drift_detection.py

Run: python app/services/drift_detection.py

Computes KS test between current PD distribution and training baseline.
Saves results to gold.model_monitoring table.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime

import numpy as np
import psycopg2
from scipy import stats

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("risklake.drift")

PG_CONN = {
    "host":     os.environ.get("PG_HOST",     "localhost"),
    "dbname":   os.environ.get("PG_DB",       "risklake"),
    "user":     os.environ.get("PG_USER",     "postgres"),
    "password": os.environ.get("PG_PASSWORD"),
}

def get_conn(): return psycopg2.connect(**PG_CONN)

def ensure_monitoring_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS gold.model_monitoring (
            id              SERIAL PRIMARY KEY,
            model_version   TEXT        NOT NULL,
            snapshot_date   DATE        NOT NULL,
            total_scored    INTEGER,
            avg_pd          FLOAT,
            std_pd          FLOAT,
            pct_grade_a     FLOAT,
            pct_grade_b     FLOAT,
            pct_grade_c     FLOAT,
            pct_grade_d     FLOAT,
            pct_grade_e     FLOAT,
            ks_statistic    FLOAT,
            ks_pvalue       FLOAT,
            drift_detected  BOOLEAN,
            drift_severity  TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (model_version, snapshot_date)
        )
    """)

def get_baseline_distribution(cur) -> np.ndarray | None:
    """
    Baseline = PD distribution from the first day the model was scored.
    We use the earliest scored_at date as the training baseline reference.
    """
    cur.execute("""
        SELECT pd_probability_ens FROM gold.pd_predictions
        WHERE DATE(scored_at) = (SELECT MIN(DATE(scored_at)) FROM gold.pd_predictions)
        ORDER BY scored_at
    """)
    rows = cur.fetchall()
    if not rows:
        return None
    return np.array([float(r[0]) for r in rows])

def get_current_distribution(cur) -> tuple[np.ndarray, str, int] | None:
    """Latest day's PD distribution."""
    cur.execute("""
        SELECT pd_probability_ens, risk_grade, model_version
        FROM gold.pd_predictions
        WHERE DATE(scored_at) = (SELECT MAX(DATE(scored_at)) FROM gold.pd_predictions)
    """)
    rows = cur.fetchall()
    if not rows:
        return None, None, 0
    pds     = np.array([float(r[0]) for r in rows])
    version = rows[0][2] if rows else "v1"
    return pds, version, len(rows)

def classify_drift(ks_stat: float, ks_pvalue: float) -> tuple[bool, str]:
    """
    Classify drift severity:
      KS stat < 0.05 or p > 0.05  → No drift
      KS stat 0.05–0.10            → Minor drift
      KS stat 0.10–0.20            → Moderate drift (alert)
      KS stat > 0.20               → Severe drift (immediate action)
    """
    if ks_pvalue > 0.05 or ks_stat < 0.05:
        return False, "none"
    elif ks_stat < 0.10:
        return True,  "minor"
    elif ks_stat < 0.20:
        return True,  "moderate"
    else:
        return True,  "severe"

def run_drift_detection() -> dict:
    conn = get_conn()
    cur  = conn.cursor()
    ensure_monitoring_table(cur)
    conn.commit()

    baseline = get_baseline_distribution(cur)
    current, version, total = get_current_distribution(cur)

    if baseline is None or current is None or total == 0:
        conn.close()
        log.warning("Not enough data to compute drift.")
        return {"error": "Insufficient data"}

    # KS test
    ks_stat, ks_pvalue = stats.ks_2samp(baseline, current)
    drift_detected, drift_severity = classify_drift(ks_stat, ks_pvalue)

    # Grade distribution
    cur.execute("""
        SELECT risk_grade, COUNT(*) FROM gold.pd_predictions
        WHERE DATE(scored_at) = (SELECT MAX(DATE(scored_at)) FROM gold.pd_predictions)
        GROUP BY risk_grade
    """)
    grade_counts = {r[0]: r[1] for r in cur.fetchall()}
    total_today  = sum(grade_counts.values()) or 1

    snapshot = {
        "model_version":  version,
        "snapshot_date":  datetime.utcnow().date().isoformat(),
        "total_scored":   total,
        "avg_pd":         float(np.mean(current)),
        "std_pd":         float(np.std(current)),
        "pct_grade_a":    round(grade_counts.get("A",0) / total_today * 100, 2),
        "pct_grade_b":    round(grade_counts.get("B",0) / total_today * 100, 2),
        "pct_grade_c":    round(grade_counts.get("C",0) / total_today * 100, 2),
        "pct_grade_d":    round(grade_counts.get("D",0) / total_today * 100, 2),
        "pct_grade_e":    round(grade_counts.get("E",0) / total_today * 100, 2),
        "ks_statistic":   round(float(ks_stat), 6),
        "ks_pvalue":      round(float(ks_pvalue), 6),
        "drift_detected": drift_detected,
        "drift_severity": drift_severity,
    }

    cur.execute("""
        INSERT INTO gold.model_monitoring
            (model_version, snapshot_date, total_scored, avg_pd, std_pd,
             pct_grade_a, pct_grade_b, pct_grade_c, pct_grade_d, pct_grade_e,
             ks_statistic, ks_pvalue, drift_detected, drift_severity)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (model_version, snapshot_date) DO UPDATE SET
            ks_statistic   = EXCLUDED.ks_statistic,
            ks_pvalue      = EXCLUDED.ks_pvalue,
            drift_detected = EXCLUDED.drift_detected,
            drift_severity = EXCLUDED.drift_severity,
            created_at     = NOW()
    """, (
        snapshot["model_version"], snapshot["snapshot_date"], snapshot["total_scored"],
        snapshot["avg_pd"], snapshot["std_pd"],
        snapshot["pct_grade_a"], snapshot["pct_grade_b"], snapshot["pct_grade_c"],
        snapshot["pct_grade_d"], snapshot["pct_grade_e"],
        snapshot["ks_statistic"], snapshot["ks_pvalue"],
        snapshot["drift_detected"], snapshot["drift_severity"],
    ))
    conn.commit()
    conn.close()

    log.info("Drift detection complete: KS=%.4f p=%.4f drift=%s severity=%s",
             ks_stat, ks_pvalue, drift_detected, drift_severity)
    return snapshot

if __name__ == "__main__":
    result = run_drift_detection()
    print(json.dumps(result, indent=2, default=str))
