"""
RiskLake — Silver Transform DAG
================================
Orchestrates the Silver layer after Bronze ingestion completes.

Steps
-----
1. wait_for_bronze   — ExternalTaskSensor waits for bronze_ingest to finish
2. dbt_run_silver    — runs all Silver dbt models (stg_* + feat_*)
3. dbt_test_silver   — runs dbt tests (schema.yml + sources.yml)
4. dbt_docs_generate — regenerates the dbt docs site (data catalogue)
5. log_silver_run    — writes a Silver run summary to PostgreSQL

Schedule: Daily at 02:00 UTC  (1 hour after Bronze DAG at 01:00)

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

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(os.environ.get("RISKLAKE_ROOT", "/opt/airflow/risklake"))
DBT_PROJECT  = PROJECT_ROOT / "dbt"

PG_CONN = {
    "host":     os.environ.get("PG_HOST",     "postgres"),
    "port":     int(os.environ.get("PG_PORT", "5432")),
    "dbname":   os.environ.get("PG_DB",       "risklake"),
    "user":     os.environ.get("PG_USER",     "risklake"),
    "password": os.environ.get("PG_PASSWORD"),
}


def _run_dbt(command: list[str]) -> dict:
    """
    Run a dbt CLI command inside the dbt project directory.
    Returns the parsed run_results.json summary.
    """
    full_cmd = ["dbt"] + command + ["--project-dir", str(DBT_PROJECT)]
    log.info("Running: %s", " ".join(full_cmd))

    result = subprocess.run(
        full_cmd,
        capture_output=True,
        text=True,
        cwd=str(DBT_PROJECT),
    )

    log.info(result.stdout)
    if result.returncode != 0:
        log.error(result.stderr)
        raise RuntimeError(f"dbt command failed: {' '.join(command)}\n{result.stderr}")

    # Parse run results for audit logging
    results_path = DBT_PROJECT / "target" / "run_results.json"
    if results_path.exists():
        with open(results_path) as f:
            return json.load(f)
    return {}


def dbt_run_silver(**context) -> None:
    """Run dbt models tagged 'silver' only."""
    _run_dbt(["run", "--select", "tag:silver"])
    log.info("dbt Silver models completed.")


def dbt_test_silver(**context) -> None:
    """Run dbt tests for Silver models. Fails task if any test fails."""
    results = _run_dbt(["test", "--select", "tag:silver"])

    # Count failures and surface them clearly
    failures = [
        r for r in results.get("results", [])
        if r.get("status") == "fail"
    ]
    if failures:
        failed_names = [r.get("unique_id") for r in failures]
        raise RuntimeError(f"dbt tests failed: {failed_names}")

    log.info("All dbt Silver tests passed.")


def dbt_docs_generate(**context) -> None:
    """Regenerate dbt docs (serves as the RiskLake data catalogue)."""
    _run_dbt(["docs", "generate"])
    log.info("dbt docs regenerated.")


def log_silver_run(**context) -> None:
    """Write a Silver run summary row to PostgreSQL for observability."""
    run_id         = context["run_id"]
    execution_date = context["execution_date"]

    conn = psycopg2.connect(**PG_CONN)

    # Ensure silver audit table exists
    with conn.cursor() as cur:
        cur.execute("""
            CREATE SCHEMA IF NOT EXISTS silver;
            CREATE TABLE IF NOT EXISTS silver.pipeline_runs (
                id             SERIAL PRIMARY KEY,
                run_id         TEXT        NOT NULL,
                execution_date DATE        NOT NULL,
                status         TEXT        NOT NULL,
                models_run     INTEGER,
                tests_passed   INTEGER,
                tests_failed   INTEGER,
                completed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)
    conn.commit()

    # Parse most recent run_results.json for counts
    results_path = DBT_PROJECT / "target" / "run_results.json"
    models_run = tests_passed = tests_failed = 0
    if results_path.exists():
        with open(results_path) as f:
            rr = json.load(f)
        for r in rr.get("results", []):
            if r.get("status") == "success":
                tests_passed += 1
            elif r.get("status") == "fail":
                tests_failed += 1
        models_run = len(rr.get("results", []))

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO silver.pipeline_runs
                (run_id, execution_date, status, models_run, tests_passed, tests_failed)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            run_id,
            execution_date.date(),
            "success" if tests_failed == 0 else "partial",
            models_run,
            tests_passed,
            tests_failed,
        ))
    conn.commit()
    conn.close()
    log.info("Silver run logged: %d models, %d passed, %d failed", models_run, tests_passed, tests_failed)


# ── DAG definition ──────────────────────────────────────────────────────────

default_args = {
    "owner":            "risklake",
    "depends_on_past":  False,
    "retries":          1,
    "retry_delay":      timedelta(minutes=10),
    "email_on_failure": False,
}

with DAG(
    dag_id="silver_transform",
    description="RiskLake — run dbt Silver models after Bronze ingestion",
    default_args=default_args,
    start_date=days_ago(1),
    schedule_interval="0 2 * * *",   # 02:00 UTC — 1h after Bronze
    catchup=False,
    max_active_runs=1,
    tags=["risklake", "silver", "dbt"],
) as dag:

    wait_for_bronze = ExternalTaskSensor(
        task_id="wait_for_bronze",
        external_dag_id="bronze_ingest",
        external_task_id=None,          # wait for the whole DAG to complete
        allowed_states=["success"],
        timeout=3600,
        poke_interval=60,
        mode="reschedule",
    )

    run_silver = PythonOperator(
        task_id="dbt_run_silver",
        python_callable=dbt_run_silver,
    )

    test_silver = PythonOperator(
        task_id="dbt_test_silver",
        python_callable=dbt_test_silver,
    )

    gen_docs = PythonOperator(
        task_id="dbt_docs_generate",
        python_callable=dbt_docs_generate,
    )

    log_run = PythonOperator(
        task_id="log_silver_run",
        python_callable=log_silver_run,
    )

    # ── Linear pipeline ──────────────────────────────────────────────────────
    wait_for_bronze >> run_silver >> test_silver >> gen_docs >> log_run
