"""
RiskLake — Gold Layer
Model  : Probability of Default (PD) — Random Forest + Logistic Regression Ensemble
Script : ml/train_pd_model.py

Purpose
-------
Trains a two-model ensemble for predicting Probability of Default (PD):
  1. Random Forest     — captures non-linear interactions (primary model)
  2. Logistic Regression — linear baseline, interpretable coefficients

Then computes SHAP values on the Random Forest to explain every prediction
in plain, audit-ready terms. SHAP values are persisted to PostgreSQL so the
FastAPI /explain endpoint and the RAG AI credit analyst can consume them.

Input tables (Silver layer — built by dbt)
------------------------------------------
  silver_silver.feat_dti_ratio    — DTI ratio, LTI, credit tier, employment type
  silver_silver.feat_credit_util  — utilisation, EMI regularity, stress score

Output artefacts
----------------
  ml/models/rf_pd_model.pkl          — trained Random Forest
  ml/models/lr_pd_model.pkl          — trained Logistic Regression
  ml/models/feature_columns.json     — ordered feature list for inference
  ml/models/model_metadata.json      — AUC, version, ensemble weights
  ml/reports/classification_report.txt
  ml/reports/roc_auc_plot.png
  ml/reports/shap_summary_plot.png
  gold.pd_predictions (PostgreSQL)   — scored customers + PD probability
  gold.shap_values    (PostgreSQL)   — per-customer per-feature SHAP values

Author : Randeep Raj
Project: RiskLake
"""

from __future__ import annotations

import json
import logging
import os
import pickle
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import psycopg2
import shap
from psycopg2.extras import execute_values
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    classification_report,
    roc_auc_score,
    RocCurveDisplay,
    precision_recall_curve,
    average_precision_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

# ── Paths ────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(os.environ.get("RISKLAKE_ROOT", Path(__file__).resolve().parents[1]))
MODELS_DIR   = PROJECT_ROOT / "ml" / "models"
REPORTS_DIR  = PROJECT_ROOT / "ml" / "reports"
MODELS_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("risklake.pd_model")

# ── Database ──────────────────────────────────────────────────────────────────

PG_CONN = {
    "host":     os.environ.get("PG_HOST",     "localhost"),
    "port":     int(os.environ.get("PG_PORT", "5432")),
    "dbname":   os.environ.get("PG_DB",       "risklake"),
    "user":     os.environ.get("PG_USER",     "risklake"),
    "password": os.environ.get("PG_PASSWORD"),
}


def get_pg_conn():
    return psycopg2.connect(**PG_CONN)


# ── Feature definition ────────────────────────────────────────────────────────

NUMERIC_FEATURES = [
    # From feat_dti_ratio
    "loan_amount_inr",
    "annual_income_inr",
    "loan_term_months",
    "existing_loans",
    "collateral_coverage_ratio",
    "loan_to_income_ratio",
    "credit_score",
    "dti_ratio",
    "monthly_income_inr",
    "estimated_monthly_emi_inr",
    "bureau_monthly_burden_inr",
    "total_monthly_debt_inr",
    "delinquency_rate",
    "hard_inquiries_6m",
    # From feat_credit_util
    "bureau_utilisation_pct",
    "avg_monthly_spend_inr",
    "spend_volatility_inr",
    "emi_payment_count_12m",
    "emi_regularity_score",
    "credit_stress_score",
    "flagged_txn_rate",
    "total_txns_12m",
]

CATEGORICAL_FEATURES = [
    "employment_type",
    "loan_purpose",
    "dti_risk_tier",
    "credit_risk_tier",
    "utilisation_band",
    "credit_age_band",
]

TARGET = "default_flag"


# ═══════════════════════════════════════════════════════════════════════════════
# 1. DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════════

def load_training_data() -> pd.DataFrame:
    """Join feat_dti_ratio and feat_credit_util from Silver and return as one DataFrame."""
    log.info("Loading Silver feature tables from PostgreSQL...")
    conn = get_pg_conn()

    query = """
        SELECT
            d.application_id,
            d.customer_id,
            d.application_date,
            d.loan_amount_inr,
            d.annual_income_inr,
            d.loan_term_months,
            d.existing_loans,
            d.collateral_coverage_ratio,
            d.loan_to_income_ratio,
            d.credit_score,
            d.employment_type,
            d.loan_purpose,
            d.dti_ratio,
            d.dti_risk_tier,
            d.credit_risk_tier,
            d.monthly_income_inr,
            d.estimated_monthly_emi_inr,
            d.bureau_monthly_burden_inr,
            d.total_monthly_debt_inr,
            d.delinquency_rate,
            d.hard_inquiries_6m,
            d.combined_risk_flag,
            d.no_bureau_record_flag,
            COALESCE(u.bureau_utilisation_pct,  0)        AS bureau_utilisation_pct,
            COALESCE(u.avg_monthly_spend_inr,   0)        AS avg_monthly_spend_inr,
            COALESCE(u.spend_volatility_inr,    0)        AS spend_volatility_inr,
            COALESCE(u.emi_payment_count_12m,   0)        AS emi_payment_count_12m,
            COALESCE(u.emi_regularity_score,    0)        AS emi_regularity_score,
            COALESCE(u.credit_stress_score,     0)        AS credit_stress_score,
            COALESCE(u.flagged_txn_rate,        0)        AS flagged_txn_rate,
            COALESCE(u.total_txns_12m,          0)        AS total_txns_12m,
            COALESCE(u.balance_trend_flag,      0)        AS balance_trend_flag,
            COALESCE(u.utilisation_change_flag, 0)        AS utilisation_change_flag,
            COALESCE(u.utilisation_band,   'unknown')     AS utilisation_band,
            COALESCE(u.credit_age_band,    'unknown')     AS credit_age_band,
            d.default_flag
        FROM silver_silver.feat_dti_ratio d
        LEFT JOIN silver_silver.feat_credit_util u USING (customer_id)
        WHERE d.default_flag IS NOT NULL
    """

    df = pd.read_sql(query, conn)
    conn.close()
    log.info("Loaded %d rows, %d columns. Default rate: %.2f%%",
             len(df), len(df.columns), df[TARGET].mean() * 100)
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# 2. FEATURE ENGINEERING
# ═══════════════════════════════════════════════════════════════════════════════

def engineer_features(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Impute nulls, one-hot encode categoricals, return feature matrix and column list."""
    log.info("Engineering features...")

    for col in NUMERIC_FEATURES:
        if col in df.columns:
            median_val = df[col].median()
            null_count = df[col].isna().sum()
            if null_count > 0:
                log.warning("  Imputing %d nulls in '%s' with median %.4f", null_count, col, median_val)
            df[col] = df[col].fillna(median_val)

    for col in CATEGORICAL_FEATURES:
        if col in df.columns:
            df[col] = df[col].fillna("unknown")

    df_encoded = pd.get_dummies(df, columns=CATEGORICAL_FEATURES, drop_first=False)

    ohe_cols     = [c for c in df_encoded.columns
                    if any(c.startswith(cat + "_") for cat in CATEGORICAL_FEATURES)]
    feature_cols = [c for c in (NUMERIC_FEATURES + ohe_cols) if c in df_encoded.columns]

    log.info("Final feature count: %d", len(feature_cols))
    return df_encoded, feature_cols


# ═══════════════════════════════════════════════════════════════════════════════
# 3. MODEL TRAINING
# ═══════════════════════════════════════════════════════════════════════════════

def train_random_forest(X_train: pd.DataFrame, y_train: pd.Series) -> RandomForestClassifier:
    """
    Train the primary Random Forest PD model.

    Key hyperparameter choices for banking credit risk:
      n_estimators=300    — stable probability estimates
      max_depth=12        — prevents memorising small applicant cohorts
      min_samples_leaf=10 — every leaf represents at least 10 applicants
      class_weight=balanced — handles imbalanced default rate
    """
    log.info("Training Random Forest...")
    rf = RandomForestClassifier(
        n_estimators=300,
        max_depth=12,
        min_samples_split=20,
        min_samples_leaf=10,
        max_features="sqrt",
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    rf.fit(X_train, y_train)
    log.info("RF trained on %d samples with %d features.", len(X_train), X_train.shape[1])
    return rf


def train_logistic_regression(X_train: pd.DataFrame, y_train: pd.Series) -> Pipeline:
    """Train a StandardScaler + LogisticRegression pipeline as the linear baseline."""
    log.info("Training Logistic Regression baseline...")
    lr_pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("lr", LogisticRegression(
            C=1.0,
            max_iter=1000,
            class_weight="balanced",
            solver="lbfgs",
            random_state=42,
        )),
    ])
    lr_pipeline.fit(X_train, y_train)
    log.info("LR pipeline trained.")
    return lr_pipeline


def evaluate_models(
    rf: RandomForestClassifier,
    lr: Pipeline,
    X_test: pd.DataFrame,
    y_test: pd.Series,
) -> dict:
    """Evaluate RF + LR + ensemble. Save classification report and ROC/PR plot."""
    log.info("Evaluating models on test set (%d samples)...", len(X_test))

    rf_proba       = rf.predict_proba(X_test)[:, 1]
    lr_proba       = lr.predict_proba(X_test)[:, 1]
    ensemble_proba = 0.70 * rf_proba + 0.30 * lr_proba
    ensemble_pred  = (ensemble_proba >= 0.5).astype(int)

    rf_auc        = roc_auc_score(y_test, rf_proba)
    lr_auc        = roc_auc_score(y_test, lr_proba)
    ensemble_auc  = roc_auc_score(y_test, ensemble_proba)
    avg_prec      = average_precision_score(y_test, ensemble_proba)

    log.info("RF AUC:        %.4f", rf_auc)
    log.info("LR AUC:        %.4f", lr_auc)
    log.info("Ensemble AUC:  %.4f", ensemble_auc)
    log.info("Avg Precision: %.4f", avg_prec)

    # Classification report
    report = classification_report(y_test, ensemble_pred, target_names=["no_default", "default"])
    report_text = (
        f"RiskLake PD Model — Classification Report\n"
        f"Generated: {datetime.utcnow().isoformat()}\n\n"
        f"RF AUC:        {rf_auc:.4f}\n"
        f"LR AUC:        {lr_auc:.4f}\n"
        f"Ensemble AUC:  {ensemble_auc:.4f}\n"
        f"Avg Precision: {avg_prec:.4f}\n\n"
        f"{report}"
    )
    (REPORTS_DIR / "classification_report.txt").write_text(report_text)
    log.info("Classification report saved.")

    # ROC + Precision-Recall plot
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    RocCurveDisplay.from_predictions(y_test, rf_proba,       ax=axes[0], name="Random Forest")
    RocCurveDisplay.from_predictions(y_test, lr_proba,       ax=axes[0], name="Logistic Regression")
    RocCurveDisplay.from_predictions(y_test, ensemble_proba, ax=axes[0], name="Ensemble (70/30)")
    axes[0].plot([0, 1], [0, 1], "k--", alpha=0.4)
    axes[0].set_title("ROC Curves — RiskLake PD Model")

    prec, rec, _ = precision_recall_curve(y_test, ensemble_proba)
    axes[1].plot(rec, prec, color="steelblue", lw=2)
    axes[1].fill_between(rec, prec, alpha=0.15, color="steelblue")
    axes[1].set_xlabel("Recall")
    axes[1].set_ylabel("Precision")
    axes[1].set_title(f"Precision-Recall — AP={avg_prec:.3f}")

    plt.tight_layout()
    plt.savefig(REPORTS_DIR / "roc_auc_plot.png", dpi=150, bbox_inches="tight")
    plt.close()
    log.info("ROC/PR plot saved.")

    return {
        "rf_auc": rf_auc,
        "lr_auc": lr_auc,
        "ensemble_auc": ensemble_auc,
        "avg_precision": avg_prec,
    }


def cross_validate_rf(rf: RandomForestClassifier, X: pd.DataFrame, y: pd.Series) -> None:
    """5-fold stratified CV to confirm stable AUC across data splits."""
    log.info("Running 5-fold stratified cross-validation...")
    cv     = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    scores = cross_val_score(rf, X, y, cv=cv, scoring="roc_auc", n_jobs=-1)
    log.info("CV AUC: %.4f +/- %.4f  | folds: %s",
             scores.mean(), scores.std(),
             ", ".join(f"{s:.4f}" for s in scores))


# ═══════════════════════════════════════════════════════════════════════════════
# 4. SHAP EXPLAINABILITY
# ═══════════════════════════════════════════════════════════════════════════════

def compute_shap_values(
    rf: RandomForestClassifier,
    X_explain: pd.DataFrame,
    feature_cols: list[str],
    sample_size: int = 200,
) -> tuple[np.ndarray, pd.DataFrame]:
    """
    Compute SHAP values using TreeExplainer (exact, native for Random Forests).

    Returns class-1 (default) SHAP values and the sampled DataFrame.
    Shape of returned array: (n_samples, n_features)
    """
    log.info("Computing SHAP values for %d samples...", min(sample_size, len(X_explain)))

    X_sample    = X_explain.sample(n=min(sample_size, len(X_explain)), random_state=42).reset_index(drop=True)
    explainer   = shap.TreeExplainer(rf)
    shap_output = explainer(X_sample[feature_cols])

    shap_vals = shap_output.values
    # TreeExplainer returns (n_samples, n_features, n_classes) for classifiers
    if shap_vals.ndim == 3:
        shap_vals = shap_vals[:, :, 1]   # class 1 = default

    log.info("SHAP array shape: %s", shap_vals.shape)
    return shap_vals, X_sample


def plot_shap_summary(
    shap_vals: np.ndarray,
    X_sample: pd.DataFrame,
    feature_cols: list[str],
) -> None:
    """Beeswarm plot — shows direction and magnitude of each feature's impact on default risk."""
    log.info("Generating SHAP summary plot...")
    plt.figure(figsize=(12, 8))
    shap.summary_plot(
        shap_vals,
        X_sample[feature_cols],
        plot_type="dot",
        max_display=20,
        show=False,
    )
    plt.title("RiskLake PD Model — SHAP Feature Importance (Top 20)", fontsize=13)
    plt.tight_layout()
    plt.savefig(REPORTS_DIR / "shap_summary_plot.png", dpi=150, bbox_inches="tight")
    plt.close()
    log.info("SHAP summary plot saved.")


def get_top_shap_reasons(
    shap_row: np.ndarray,
    feature_cols: list[str],
    top_n: int = 10,
) -> list[dict]:
    """
    Convert one SHAP row into a ranked list of human-readable risk drivers.
    Consumed by the FastAPI /explain endpoint and the RAG credit analyst prompt.

    Example:
      [
        {"feature": "dti_ratio",           "shap_value": 0.18, "direction": "increases_risk"},
        {"feature": "emi_regularity_score", "shap_value":-0.09, "direction": "decreases_risk"},
      ]
    """
    ranked = sorted(zip(feature_cols, shap_row), key=lambda x: abs(x[1]), reverse=True)[:top_n]
    return [
        {
            "feature":    feat,
            "shap_value": round(float(val), 6),
            "direction":  "increases_risk" if val > 0 else "decreases_risk",
        }
        for feat, val in ranked
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# 5. PERSIST TO POSTGRESQL (Gold layer)
# ═══════════════════════════════════════════════════════════════════════════════

def ensure_gold_schema(conn) -> None:
    ddl = """
    CREATE SCHEMA IF NOT EXISTS gold;

    CREATE TABLE IF NOT EXISTS gold.pd_predictions (
        id                 SERIAL PRIMARY KEY,
        application_id     TEXT        NOT NULL,
        customer_id        TEXT        NOT NULL,
        pd_probability_rf  FLOAT       NOT NULL,
        pd_probability_lr  FLOAT       NOT NULL,
        pd_probability_ens FLOAT       NOT NULL,
        pd_prediction      INTEGER     NOT NULL,
        risk_grade         TEXT        NOT NULL,
        model_version      TEXT        NOT NULL,
        scored_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (application_id, model_version)
    );

    CREATE TABLE IF NOT EXISTS gold.shap_values (
        id             SERIAL PRIMARY KEY,
        application_id TEXT        NOT NULL,
        customer_id    TEXT        NOT NULL,
        feature_name   TEXT        NOT NULL,
        shap_value     FLOAT       NOT NULL,
        direction      TEXT        NOT NULL,
        rank           INTEGER     NOT NULL,
        model_version  TEXT        NOT NULL,
        computed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_pd_app   ON gold.pd_predictions (application_id);
    CREATE INDEX IF NOT EXISTS idx_shap_app ON gold.shap_values    (application_id);
    """
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()
    log.info("Gold schema and tables verified.")


def pd_to_risk_grade(pd_prob: float) -> str:
    """Basel II-aligned risk grade. A = lowest risk, E = highest."""
    if pd_prob < 0.05: return "A"
    if pd_prob < 0.15: return "B"
    if pd_prob < 0.30: return "C"
    if pd_prob < 0.50: return "D"
    return "E"


def persist_predictions(
    conn,
    df_full: pd.DataFrame,
    rf: RandomForestClassifier,
    lr: Pipeline,
    feature_cols: list[str],
    model_version: str,
) -> None:
    """Score every application and upsert into gold.pd_predictions."""
    log.info("Scoring all %d applications...", len(df_full))
    X_all        = df_full[feature_cols].fillna(0)
    rf_proba_all = rf.predict_proba(X_all)[:, 1]
    lr_proba_all = lr.predict_proba(X_all)[:, 1]
    ens_proba    = 0.70 * rf_proba_all + 0.30 * lr_proba_all
    predictions  = (ens_proba >= 0.5).astype(int)

    rows = [
        (
            str(df_full.iloc[i]["application_id"]),
            str(df_full.iloc[i]["customer_id"]),
            float(rf_proba_all[i]),
            float(lr_proba_all[i]),
            float(ens_proba[i]),
            int(predictions[i]),
            pd_to_risk_grade(float(ens_proba[i])),
            model_version,
        )
        for i in range(len(df_full))
    ]

    sql = """
        INSERT INTO gold.pd_predictions
            (application_id, customer_id, pd_probability_rf, pd_probability_lr,
             pd_probability_ens, pd_prediction, risk_grade, model_version)
        VALUES %s
        ON CONFLICT (application_id, model_version)
        DO UPDATE SET
            pd_probability_rf  = EXCLUDED.pd_probability_rf,
            pd_probability_lr  = EXCLUDED.pd_probability_lr,
            pd_probability_ens = EXCLUDED.pd_probability_ens,
            pd_prediction      = EXCLUDED.pd_prediction,
            risk_grade         = EXCLUDED.risk_grade,
            scored_at          = NOW()
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, rows)
    conn.commit()
    log.info("Persisted %d PD predictions to gold.pd_predictions.", len(rows))


def persist_shap_values(
    conn,
    shap_vals: np.ndarray,
    X_sample: pd.DataFrame,
    df_sorted: pd.DataFrame,
    feature_cols: list[str],
    model_version: str,
) -> None:
    """Write top-10 SHAP features per sampled application to gold.shap_values."""
    log.info("Persisting SHAP values for %d applications...", len(X_sample))
    rows = []
    for i in range(len(X_sample)):
        original_idx = X_sample.index[i]
        app_id       = str(df_sorted.iloc[original_idx]["application_id"])
        customer_id  = str(df_sorted.iloc[original_idx]["customer_id"])
        reasons      = get_top_shap_reasons(shap_vals[i], feature_cols, top_n=10)
        for rank, reason in enumerate(reasons, start=1):
            rows.append((app_id, customer_id, reason["feature"],
                         reason["shap_value"], reason["direction"], rank, model_version))

    sql = """
        INSERT INTO gold.shap_values
            (application_id, customer_id, feature_name, shap_value, direction, rank, model_version)
        VALUES %s
        ON CONFLICT DO NOTHING
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, rows)
    conn.commit()
    log.info("SHAP values persisted.")


# ═══════════════════════════════════════════════════════════════════════════════
# 6. SAVE ARTEFACTS
# ═══════════════════════════════════════════════════════════════════════════════

def save_artefacts(
    rf: RandomForestClassifier,
    lr: Pipeline,
    feature_cols: list[str],
    metrics: dict,
    model_version: str,
) -> None:
    with open(MODELS_DIR / "rf_pd_model.pkl",      "wb") as f: pickle.dump(rf, f)
    with open(MODELS_DIR / "lr_pd_model.pkl",      "wb") as f: pickle.dump(lr, f)
    with open(MODELS_DIR / "feature_columns.json", "w")  as f: json.dump(feature_cols, f, indent=2)
    with open(MODELS_DIR / "model_metadata.json",  "w")  as f:
        json.dump({
            "model_version":    model_version,
            "trained_at":       datetime.utcnow().isoformat(),
            "ensemble_weights": {"rf": 0.70, "lr": 0.30},
            "feature_count":    len(feature_cols),
            **metrics,
        }, f, indent=2)
    log.info("All artefacts saved to %s", MODELS_DIR)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    model_version = f"v{datetime.utcnow().strftime('%Y%m%d_%H%M')}"
    log.info("=" * 62)
    log.info("RiskLake PD Model Training  —  %s", model_version)
    log.info("=" * 62)

    # 1. Load
    df_raw = load_training_data()

    # 2. Feature engineering
    df, feature_cols = engineer_features(df_raw.copy())

    # 3. Time-ordered train/test split (80/20) — avoids data leakage
    df_sorted  = df.sort_values("application_date").reset_index(drop=True)
    split_idx  = int(len(df_sorted) * 0.80)
    X_train    = df_sorted.iloc[:split_idx][feature_cols]
    y_train    = df_sorted.iloc[:split_idx][TARGET]
    X_test     = df_sorted.iloc[split_idx:][feature_cols]
    y_test     = df_sorted.iloc[split_idx:][TARGET]
    log.info("Train: %d  |  Test: %d", len(X_train), len(X_test))

    # 4. Train
    rf = train_random_forest(X_train, y_train)
    lr = train_logistic_regression(X_train, y_train)

    # 5. Cross-validate
    cross_validate_rf(rf, df_sorted[feature_cols], df_sorted[TARGET])

    # 6. Evaluate
    metrics = evaluate_models(rf, lr, X_test, y_test)

    # 7. SHAP
    shap_vals, X_sample = compute_shap_values(rf, X_test, feature_cols, sample_size=200)
    plot_shap_summary(shap_vals, X_sample, feature_cols)

    # 8. Persist to Gold
    conn = get_pg_conn()
    ensure_gold_schema(conn)
    persist_predictions(conn, df_sorted, rf, lr, feature_cols, model_version)
    persist_shap_values(conn, shap_vals, X_sample, df_sorted, feature_cols, model_version)
    conn.close()

    # 9. Save artefacts
    save_artefacts(rf, lr, feature_cols, metrics, model_version)

    log.info("=" * 62)
    log.info("Training complete  |  Ensemble AUC: %.4f", metrics["ensemble_auc"])
    log.info("=" * 62)


if __name__ == "__main__":
    main()
