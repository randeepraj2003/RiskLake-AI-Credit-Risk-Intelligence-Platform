"""
RiskLake - Complete risk.py with ALL endpoints including:
- Original: predict, explain, portfolio, batch, customer, cache, decide, batch-csv
- NEW: /models, /models/{version}, /models/{version}/promote
- NEW: /monitoring, /monitoring/latest
File: backend/app/routers/risk.py
"""
import psycopg2
import os
import csv
import io
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from decimal import Decimal

from app.services.decision_engine import make_decision

router = APIRouter(prefix="/risk", tags=["Credit Risk"])

PG_CONN = {
    "host":     os.environ.get("PG_HOST", "localhost"),
    "dbname":   os.environ.get("PG_DB",   "risklake"),
    "user":     os.environ.get("PG_USER", "postgres"),
    "password": os.environ.get("PG_PASSWORD"),
}

def get_conn():
    return psycopg2.connect(**PG_CONN)

def safe(val):
    if isinstance(val, Decimal): return float(val)
    return val

# ── Predict ───────────────────────────────────────────────────────────────────

@router.get("/predict/{application_id}")
async def predict(application_id: str, model_version: str = None):
    try:
        conn = get_conn()
        cur  = conn.cursor()
        if model_version:
            cur.execute("""
                SELECT p.application_id, p.customer_id, p.pd_probability_rf,
                       p.pd_probability_lr, p.pd_probability_ens,
                       p.pd_prediction, p.risk_grade, p.model_version,
                       d.loan_amount_inr, d.annual_income_inr, d.employment_type,
                       d.loan_purpose, d.credit_score, d.loan_to_income_ratio,
                       d.dti_ratio, d.dti_risk_tier, d.credit_risk_tier
                FROM gold.pd_predictions p
                LEFT JOIN silver_silver.feat_dti_ratio d ON p.application_id = d.application_id
                WHERE p.application_id = %s AND p.model_version = %s
                ORDER BY p.scored_at DESC LIMIT 1
            """, (application_id.upper(), model_version))
        else:
            cur.execute("""
                SELECT p.application_id, p.customer_id, p.pd_probability_rf,
                       p.pd_probability_lr, p.pd_probability_ens,
                       p.pd_prediction, p.risk_grade, p.model_version,
                       d.loan_amount_inr, d.annual_income_inr, d.employment_type,
                       d.loan_purpose, d.credit_score, d.loan_to_income_ratio,
                       d.dti_ratio, d.dti_risk_tier, d.credit_risk_tier
                FROM gold.pd_predictions p
                LEFT JOIN silver_silver.feat_dti_ratio d ON p.application_id = d.application_id
                WHERE p.application_id = %s
                ORDER BY p.scored_at DESC LIMIT 1
            """, (application_id.upper(),))
        row = cur.fetchone()
        conn.close()
        if not row:
            raise HTTPException(status_code=404, detail=f"{application_id} not found")
        return {
            "application_id":       row[0],
            "customer_id":          row[1],
            "pd_probability_rf":    safe(row[2]),
            "pd_probability_lr":    safe(row[3]),
            "pd_probability_ens":   safe(row[4]),
            "pd_prediction":        row[5],
            "risk_grade":           row[6],
            "model_version":        row[7],
            "loan_amount_inr":      safe(row[8]),
            "annual_income_inr":    safe(row[9]),
            "employment_type":      row[10],
            "loan_purpose":         row[11],
            "credit_score":         safe(row[12]),
            "loan_to_income_ratio": safe(row[13]),
            "dti_ratio":            safe(row[14]),
            "dti_risk_tier":        row[15],
            "credit_risk_tier":     row[16],
            "cache_hit":            False,
            "latency_ms":           0,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Explain ───────────────────────────────────────────────────────────────────

@router.get("/explain/{application_id}")
async def explain(application_id: str, top_n: int = 10):
    try:
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute("""
            SELECT feature_name, shap_value, direction, rank
            FROM gold.shap_values
            WHERE application_id = %s
            ORDER BY rank ASC LIMIT %s
        """, (application_id.upper(), top_n))
        rows = cur.fetchall()
        conn.close()
        return {
            "application_id": application_id,
            "model_version":  "v1",
            "risk_drivers": [
                {"rank": r[3], "feature": r[0],
                 "shap_value": float(r[1]), "direction": r[2],
                 "label": r[0].replace("_"," ")}
                for r in rows
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Portfolio ─────────────────────────────────────────────────────────────────

@router.get("/portfolio")
async def portfolio():
    try:
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute("""
            SELECT risk_grade, COUNT(*) as count, AVG(pd_probability_ens) as avg_pd
            FROM gold.pd_predictions GROUP BY risk_grade ORDER BY risk_grade
        """)
        grades = [{"risk_grade": r[0], "count": r[1], "avg_pd": float(r[2])} for r in cur.fetchall()]
        cur.execute("SELECT COUNT(*), AVG(pd_probability_ens) FROM gold.pd_predictions")
        total_row = cur.fetchone()
        cur.execute("SELECT COUNT(*) FROM gold.pd_predictions WHERE risk_grade IN ('D','E')")
        high_risk = cur.fetchone()[0]
        cur.execute("""
            SELECT DATE(scored_at) as day, AVG(pd_probability_ens) as avg_pd, COUNT(*) as cnt
            FROM gold.pd_predictions
            GROUP BY DATE(scored_at) ORDER BY day DESC LIMIT 30
        """)
        trend = [{"date": str(r[0]), "avg_pd": float(r[1]), "scored_count": r[2]} for r in cur.fetchall()]
        conn.close()
        total  = total_row[0] or 0
        avg_pd = float(total_row[1]) if total_row[1] else 0
        return {
            "total_applications": total,
            "portfolio_avg_pd":   avg_pd,
            "high_risk_count":    high_risk,
            "high_risk_pct":      (high_risk / total * 100) if total > 0 else 0,
            "grade_distribution": grades,
            "pd_trend_30d":       trend,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Batch predict ─────────────────────────────────────────────────────────────

@router.post("/predict/batch")
async def batch_predict(payload: dict):
    ids = payload.get("application_ids", [])[:100]
    results, errors = [], []
    for app_id in ids:
        try:
            results.append(await predict(app_id))
        except Exception as e:
            errors.append({"application_id": app_id, "error": str(e)})
    return {"results": results, "errors": errors}

# ── Customer ──────────────────────────────────────────────────────────────────

@router.get("/customer/{customer_id}")
async def customer(customer_id: str):
    try:
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute("""
            SELECT application_id FROM gold.pd_predictions
            WHERE customer_id = %s ORDER BY scored_at DESC
        """, (customer_id,))
        app_ids = [r[0] for r in cur.fetchall()]
        conn.close()
        results = []
        for app_id in app_ids:
            try:
                results.append(await predict(app_id))
            except:
                pass
        return {"customer_id": customer_id, "applications": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Cache ─────────────────────────────────────────────────────────────────────

@router.delete("/cache/{application_id}")
async def clear_cache(application_id: str):
    return {"cleared": application_id}

# ── Decide ────────────────────────────────────────────────────────────────────

@router.get("/decide/{application_id}")
async def decide(application_id: str):
    pred   = await predict(application_id)
    result = make_decision(
        risk_grade         = pred.get("risk_grade"),
        pd_probability_ens = pred.get("pd_probability_ens", 0),
        dti_ratio          = pred.get("dti_ratio"),
        dti_risk_tier      = pred.get("dti_risk_tier"),
        credit_score       = pred.get("credit_score"),
    )
    return {"application_id": application_id, "customer_id": pred.get("customer_id"),
            "risk_grade": pred.get("risk_grade"), "pd_probability_ens": pred.get("pd_probability_ens"),
            **result}

# ── Batch CSV ─────────────────────────────────────────────────────────────────

@router.post("/predict/batch-csv")
async def predict_batch_csv(file: UploadFile = File(...)):
    raw  = await file.read()
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = reader.fieldnames or []
    id_col = next((f for f in fieldnames if f.strip().lower() == "application_id"), None)
    if not id_col:
        raise HTTPException(status_code=422, detail="CSV must contain an 'application_id' column.")
    rows = list(reader)[:500]
    if not rows:
        raise HTTPException(status_code=422, detail="CSV is empty.")
    output_rows = []
    for row in rows:
        app_id = (row.get(id_col) or "").strip().upper()
        if not app_id:
            continue
        try:
            pred = await predict(app_id)
            dec  = make_decision(
                risk_grade=pred.get("risk_grade"), pd_probability_ens=pred.get("pd_probability_ens",0),
                dti_ratio=pred.get("dti_ratio"), dti_risk_tier=pred.get("dti_risk_tier"),
                credit_score=pred.get("credit_score"),
            )
            output_rows.append({
                "application_id": app_id, "customer_id": pred.get("customer_id"),
                "pd_probability_rf": pred.get("pd_probability_rf"),
                "pd_probability_lr": pred.get("pd_probability_lr"),
                "pd_probability_ens": pred.get("pd_probability_ens"),
                "risk_grade": pred.get("risk_grade"), "decision": dec["decision"],
                "confidence": dec["confidence"], "reasoning": " | ".join(dec["reasoning"]), "error": "",
            })
        except HTTPException as e:
            output_rows.append({"application_id": app_id, "customer_id": "", "pd_probability_rf": "",
                "pd_probability_lr": "", "pd_probability_ens": "", "risk_grade": "",
                "decision": "", "confidence": "", "reasoning": "", "error": e.detail})
    out_buf = io.StringIO()
    writer  = csv.DictWriter(out_buf, fieldnames=[
        "application_id","customer_id","pd_probability_rf","pd_probability_lr",
        "pd_probability_ens","risk_grade","decision","confidence","reasoning","error"])
    writer.writeheader()
    writer.writerows(output_rows)
    out_buf.seek(0)
    return StreamingResponse(iter([out_buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=risklake_batch_results.csv"})

# ── Model Registry ────────────────────────────────────────────────────────────

@router.get("/models")
async def list_models():
    try:
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute("""
            SELECT model_version, rf_auc, lr_auc, ensemble_auc, avg_precision,
                   feature_count, train_rows, test_rows, status, trained_at, registered_at, notes
            FROM gold.model_registry ORDER BY registered_at DESC
        """)
        rows = cur.fetchall()
        conn.close()
        return {
            "models": [
                {"model_version": r[0], "rf_auc": safe(r[1]), "lr_auc": safe(r[2]),
                 "ensemble_auc": safe(r[3]), "avg_precision": safe(r[4]),
                 "feature_count": r[5], "train_rows": r[6], "test_rows": r[7],
                 "status": r[8], "trained_at": str(r[9]) if r[9] else None,
                 "registered_at": str(r[10]) if r[10] else None, "notes": r[11]}
                for r in rows
            ],
            "total": len(rows),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/models/{model_version}")
async def get_model(model_version: str):
    try:
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute("""
            SELECT model_version, rf_auc, lr_auc, ensemble_auc, avg_precision,
                   feature_count, train_rows, test_rows, status, trained_at, registered_at, notes
            FROM gold.model_registry WHERE model_version = %s
        """, (model_version,))
        row = cur.fetchone()
        conn.close()
        if not row:
            raise HTTPException(status_code=404, detail=f"Model {model_version} not found")
        return {"model_version": row[0], "rf_auc": safe(row[1]), "lr_auc": safe(row[2]),
                "ensemble_auc": safe(row[3]), "avg_precision": safe(row[4]),
                "feature_count": row[5], "train_rows": row[6], "test_rows": row[7],
                "status": row[8], "trained_at": str(row[9]) if row[9] else None,
                "registered_at": str(row[10]) if row[10] else None, "notes": row[11]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/models/{model_version}/promote")
async def promote_model(model_version: str):
    try:
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute("SELECT ensemble_auc, status FROM gold.model_registry WHERE model_version = %s",
                    (model_version,))
        row = cur.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail=f"Model {model_version} not found")
        if row[1] == "active":
            conn.close()
            return {"message": f"{model_version} is already active", "status": "active"}
        cur.execute("UPDATE gold.model_registry SET status='retired' WHERE status='active'")
        cur.execute("UPDATE gold.model_registry SET status='active' WHERE model_version=%s", (model_version,))
        conn.commit()
        conn.close()
        return {"message": f"{model_version} promoted to active", "model_version": model_version,
                "ensemble_auc": safe(row[0]), "status": "active"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Model Monitoring ──────────────────────────────────────────────────────────

@router.get("/monitoring")
async def get_monitoring():
    """Get full monitoring history — PD snapshots + drift flags over time."""
    try:
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute("""
            SELECT model_version, snapshot_date, total_scored, avg_pd, std_pd,
                   pct_grade_a, pct_grade_b, pct_grade_c, pct_grade_d, pct_grade_e,
                   ks_statistic, ks_pvalue, drift_detected, drift_severity, created_at
            FROM gold.model_monitoring
            ORDER BY snapshot_date DESC LIMIT 60
        """)
        rows = cur.fetchall()
        conn.close()
        return {
            "snapshots": [
                {"model_version": r[0], "snapshot_date": str(r[1]),
                 "total_scored": r[2], "avg_pd": float(r[3]) if r[3] else 0,
                 "std_pd": float(r[4]) if r[4] else 0,
                 "grade_distribution": {
                     "A": float(r[5]) if r[5] else 0, "B": float(r[6]) if r[6] else 0,
                     "C": float(r[7]) if r[7] else 0, "D": float(r[8]) if r[8] else 0,
                     "E": float(r[9]) if r[9] else 0,
                 },
                 "ks_statistic": float(r[10]) if r[10] else 0,
                 "ks_pvalue": float(r[11]) if r[11] else 0,
                 "drift_detected": r[12], "drift_severity": r[13],
                 "created_at": str(r[14]) if r[14] else None}
                for r in rows
            ],
            "total": len(rows),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/monitoring/latest")
async def get_monitoring_latest():
    """Get the most recent drift detection snapshot."""
    try:
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute("""
            SELECT model_version, snapshot_date, total_scored, avg_pd, std_pd,
                   pct_grade_a, pct_grade_b, pct_grade_c, pct_grade_d, pct_grade_e,
                   ks_statistic, ks_pvalue, drift_detected, drift_severity
            FROM gold.model_monitoring
            ORDER BY snapshot_date DESC LIMIT 1
        """)
        row = cur.fetchone()
        conn.close()
        if not row:
            return {"message": "No monitoring data yet. Run drift_detection.py first."}
        return {
            "model_version":  row[0],
            "snapshot_date":  str(row[1]),
            "total_scored":   row[2],
            "avg_pd":         float(row[3]) if row[3] else 0,
            "std_pd":         float(row[4]) if row[4] else 0,
            "grade_distribution": {
                "A": float(row[5]) if row[5] else 0, "B": float(row[6]) if row[6] else 0,
                "C": float(row[7]) if row[7] else 0, "D": float(row[8]) if row[8] else 0,
                "E": float(row[9]) if row[9] else 0,
            },
            "ks_statistic":   float(row[10]) if row[10] else 0,
            "ks_pvalue":      float(row[11]) if row[11] else 0,
            "drift_detected": row[12],
            "drift_severity": row[13],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
