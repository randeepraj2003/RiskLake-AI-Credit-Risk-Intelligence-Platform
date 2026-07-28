"""
RiskLake — Master Pipeline DAG
File: backend/dags/risklake_pipeline.py

Runs the full Bronze -> Silver -> Gold pipeline daily at 01:00.
No Docker needed — runs directly with pip-installed Airflow on Windows.

Steps:
  1. generate_mock_data  — refreshes data/raw/*.csv
  2. bronze_ingest       — loads CSVs into PostgreSQL bronze schema
  3. silver_dbt_run      — runs dbt Silver models
  4. silver_dbt_test     — runs dbt tests
  5. gold_model_train    — trains versioned PD model with --promote
  6. drift_detection     — computes KS drift vs baseline
"""

import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

log = logging.getLogger(__name__)

BACKEND  = os.environ.get("RISKLAKE_ROOT", r"C:\Users\rande\OneDrive\Desktop\risklake\risklake\backend")
PYTHON   = sys.executable
DBT_DIR  = os.path.join(BACKEND, "dbt")
PG_ENV   = {**os.environ, "PG_HOST":"localhost","PG_PORT":"5432","PG_DB":"risklake",
             "PG_USER": os.environ.get("PG_USER"), "PG_PASSWORD": os.environ.get("PG_PASSWORD"), "RISKLAKE_ROOT": BACKEND}

default_args = {
    "owner":            "risklake",
    "depends_on_past":  False,
    "retries":          1,
    "retry_delay":      timedelta(minutes=5),
    "email_on_failure": False,
}

def run_script(path, args=None):
    cmd    = [PYTHON, path] + (args or [])
    result = subprocess.run(cmd, capture_output=True, text=True, env=PG_ENV, cwd=BACKEND)
    log.info(result.stdout)
    if result.returncode != 0:
        log.error(result.stderr)
        raise RuntimeError(f"Failed: {path}\n{result.stderr}")

def run_dbt(command):
    result = subprocess.run(["dbt"] + command.split(), capture_output=True,
                            text=True, env=PG_ENV, cwd=DBT_DIR)
    log.info(result.stdout)
    if result.returncode != 0:
        log.error(result.stderr)
        raise RuntimeError(f"dbt failed: {command}\n{result.stderr}")

def task_generate_data(**ctx):
    run_script(os.path.join(BACKEND, "generate_mock_data.py"))

def task_bronze_ingest(**ctx):
    import pandas as pd
    from sqlalchemy import create_engine
    engine = create_engine("postgresql://postgres:risklake@localhost:5432/risklake")
    for tbl in ["loan_applications","credit_bureau","transactions","macro_indicators"]:
        df = pd.read_csv(os.path.join(BACKEND, "data", "raw", f"{tbl}.csv"))
        df.to_sql(tbl, engine, schema="bronze", if_exists="replace", index=False)
        log.info("Loaded %s: %d rows", tbl, len(df))

def task_silver_run(**ctx):
    run_dbt("run --select tag:silver")

def task_silver_test(**ctx):
    run_dbt("test --select tag:silver")

def task_gold_train(**ctx):
    run_script(os.path.join(BACKEND,"app","services","train_versioned.py"), ["--promote"])

def task_drift(**ctx):
    run_script(os.path.join(BACKEND,"app","services","drift_detection.py"))

with DAG(
    dag_id="risklake_pipeline",
    description="RiskLake — Bronze to Silver to Gold daily pipeline",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule_interval="0 1 * * *",
    catchup=False,
    max_active_runs=1,
    tags=["risklake","pipeline"],
) as dag:

    t1 = PythonOperator(task_id="generate_mock_data",  python_callable=task_generate_data)
    t2 = PythonOperator(task_id="bronze_ingest",        python_callable=task_bronze_ingest)
    t3 = PythonOperator(task_id="silver_dbt_run",       python_callable=task_silver_run)
    t4 = PythonOperator(task_id="silver_dbt_test",      python_callable=task_silver_test)
    t5 = PythonOperator(task_id="gold_model_train",     python_callable=task_gold_train)
    t6 = PythonOperator(task_id="drift_detection",      python_callable=task_drift)

    t1 >> t2 >> t3 >> t4 >> t5 >> t6
