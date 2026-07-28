"""
RiskLake — Gold Model Refresh DAG
====================================
Nightly retraining pipeline. Schedule: 03:00 UTC (1hr after Silver).

Steps:
  1. wait_for_silver  — ExternalTaskSensor waits for silver_transform DAG
  2. run_training     — runs ml/train_pd_model.py as subprocess
  3. validate_model   — checks ensemble AUC >= 0.70 before promoting
  4. log_model_run    — registers version in gold.model_registry

Author : Randeep Raj
Project: RiskLake
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import timedelta
from pathlib import Path

import psycopg2
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.sensors.external_task import ExternalTaskSensor
from airflow.utils.dates import days_ago

log          = logging.getLogger(__name__)
PROJECT_ROOT = Path(os.environ.get("RISKLAKE_ROOT", "/opt/airflow/risklake"))
MODELS_DIR   = PROJECT_ROOT / "ml" / "models"
AUC_THRESHOLD = 0.70

PG_CONN = {
    "host":     os.environ.get("PG_HOST",     "postgres"),
    "port":     int(os.environ.get("PG_PORT", "5432")),
    "dbname":   os.environ.get("PG_DB",       "risklake"),
    "user":     os.environ.get("PG_USER",     "risklake"),
    "password": os.environ.get("PG_PASSWORD"),
}


def run_training(**context) -> None:
    script = PROJECT_ROOT / "ml" / "train_pd_model.py"
    result = subprocess.run(["python", str(script)], capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    log.info(result.stdout)
    if result.returncode != 0:
        log.error(result.stderr)
        raise RuntimeError(f"Training failed:\n{result.stderr}")


def validate_model(**context) -> None:
    meta_path = MODELS_DIR / "model_metadata.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"model_metadata.json not found at {meta_path}")
    with open(meta_path) as f:
        meta = json.load(f)
    auc = meta.get("ensemble_auc", 0.0)
    log.info("AUC: %.4f  (threshold: %.4f)", auc, AUC_THRESHOLD)
    if auc < AUC_THRESHOLD:
        raise ValueError(f"Model rejected: AUC {auc:.4f} < threshold {AUC_THRESHOLD}")
    context["ti"].xcom_push(key="model_metadata", value=meta)


def log_model_run(**context) -> None:
    meta = context["ti"].xcom_pull(task_ids="validate_model", key="model_metadata")
    if not meta:
        return
    conn = psycopg2.connect(**PG_CONN)
    with conn.cursor() as cur:
        cur.execute("""
            CREATE SCHEMA IF NOT EXISTS gold;
            CREATE TABLE IF NOT EXISTS gold.model_registry (
                id            SERIAL PRIMARY KEY,
                model_version TEXT        NOT NULL UNIQUE,
                ensemble_auc  FLOAT,
                rf_auc        FLOAT,
                lr_auc        FLOAT,
                avg_precision FLOAT,
                feature_count INTEGER,
                status        TEXT        NOT NULL DEFAULT 'active',
                trained_at    TIMESTAMPTZ,
                registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            INSERT INTO gold.model_registry
                (model_version, ensemble_auc, rf_auc, lr_auc, avg_precision, feature_count, trained_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (model_version) DO NOTHING;
        """, (
            meta.get("model_version"), meta.get("ensemble_auc"), meta.get("rf_auc"),
            meta.get("lr_auc"), meta.get("avg_precision"), meta.get("feature_count"),
            meta.get("trained_at"),
        ))
    conn.commit()
    conn.close()
    log.info("Registered model %s  AUC=%.4f", meta.get("model_version"), meta.get("ensemble_auc"))


default_args = {"owner": "risklake", "depends_on_past": False,
                "retries": 1, "retry_delay": timedelta(minutes=15), "email_on_failure": False}

with DAG(
    dag_id="gold_model_refresh",
    description="RiskLake — nightly PD model retraining + Gold scoring",
    default_args=default_args,
    start_date=days_ago(1),
    schedule_interval="0 3 * * *",
    catchup=False,
    max_active_runs=1,
    tags=["risklake", "gold", "ml"],
) as dag:

    wait_for_silver = ExternalTaskSensor(
        task_id="wait_for_silver", external_dag_id="silver_transform",
        external_task_id=None, allowed_states=["success"],
        timeout=3600, poke_interval=60, mode="reschedule",
    )
    train    = PythonOperator(task_id="run_training",   python_callable=run_training)
    validate = PythonOperator(task_id="validate_model", python_callable=validate_model)
    register = PythonOperator(task_id="log_model_run",  python_callable=log_model_run)

    wait_for_silver >> train >> validate >> register
