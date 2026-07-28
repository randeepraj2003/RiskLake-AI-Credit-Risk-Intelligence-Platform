"""
RiskLake — Bronze Ingestion DAG
================================
Ingests raw CSV/API source data into a partitioned Parquet store (Bronze layer)
and writes a full audit trail + schema snapshot to PostgreSQL.

Schedule: Daily at 01:00 UTC
Layers:   Bronze only (no transforms — that is Silver's job)

Sources ingested:
  - loan_applications.csv
  - credit_bureau.csv
  - transactions.csv
  - macro_indicators.csv  (stubbed as CSV; swap for API call in production)

Output layout:
  data/bronze/<source_name>/year=YYYY/month=MM/day=DD/<source_name>.parquet

Audit table (PostgreSQL — bronze.audit_log):
  run_id, source_name, execution_date, row_count, file_size_bytes,
  column_names, column_dtypes, status, error_message, ingested_at

Author : Randeep Raj
Project: RiskLake
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import psycopg2
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Base project root — works whether running inside Docker or locally.
PROJECT_ROOT = Path(os.environ.get("RISKLAKE_ROOT", "/opt/airflow/risklake"))

RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
BRONZE_DIR   = PROJECT_ROOT / "data" / "bronze"

# PostgreSQL connection — set these as Airflow Variables or environment vars.
PG_CONN = {
    "host":     os.environ.get("PG_HOST",     "postgres"),
    "port":     int(os.environ.get("PG_PORT", "5432")),
    "dbname":   os.environ.get("PG_DB",       "risklake"),
    "user":     os.environ.get("PG_USER",     "risklake"),
    "password": os.environ.get("PG_PASSWORD"),
}

# Sources: name → relative path inside RAW_DATA_DIR
SOURCES = {
    "loan_applications": "loan_applications.csv",
    "credit_bureau":     "credit_bureau.csv",
    "transactions":      "transactions.csv",
    "macro_indicators":  "macro_indicators.csv",
}

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_pg_conn():
    """Return a live psycopg2 connection."""
    return psycopg2.connect(**PG_CONN)


def _ensure_audit_schema(conn) -> None:
    """Create bronze schema and audit_log table if they don't exist."""
    ddl = """
    CREATE SCHEMA IF NOT EXISTS bronze;

    CREATE TABLE IF NOT EXISTS bronze.audit_log (
        id              SERIAL PRIMARY KEY,
        run_id          TEXT        NOT NULL,
        source_name     TEXT        NOT NULL,
        execution_date  DATE        NOT NULL,
        row_count       INTEGER,
        file_size_bytes BIGINT,
        column_names    JSONB,
        column_dtypes   JSONB,
        row_hash        TEXT,
        status          TEXT        NOT NULL DEFAULT 'pending',
        error_message   TEXT,
        parquet_path    TEXT,
        ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS bronze.schema_snapshot (
        id              SERIAL PRIMARY KEY,
        source_name     TEXT        NOT NULL,
        snapshot_date   DATE        NOT NULL,
        column_names    JSONB       NOT NULL,
        column_dtypes   JSONB       NOT NULL,
        schema_hash     TEXT        NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (source_name, snapshot_date)
    );
    """
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()


def _compute_df_hash(df: pd.DataFrame) -> str:
    """
    Lightweight content fingerprint: hash the sorted column names + row count.
    Replace with a full checksum if data integrity audits are required.
    """
    fingerprint = f"{sorted(df.columns.tolist())}|{len(df)}"
    return hashlib.sha256(fingerprint.encode()).hexdigest()[:16]


def _write_parquet(df: pd.DataFrame, source_name: str, execution_date: datetime) -> Path:
    """
    Write DataFrame to partitioned Parquet:
      data/bronze/<source>/year=YYYY/month=MM/day=DD/<source>.parquet
    Returns the full path of the written file.
    """
    partition_path = (
        BRONZE_DIR
        / source_name
        / f"year={execution_date.year}"
        / f"month={execution_date.month:02d}"
        / f"day={execution_date.day:02d}"
    )
    partition_path.mkdir(parents=True, exist_ok=True)

    out_file = partition_path / f"{source_name}.parquet"
    df.to_parquet(out_file, index=False, engine="pyarrow", compression="snappy")
    log.info("Written %d rows to %s (%d bytes)", len(df), out_file, out_file.stat().st_size)
    return out_file


def _upsert_audit_row(conn, row: dict) -> None:
    """
    Insert a single audit row. On conflict (run_id + source_name), update
    status, row_count, and any enriched fields.
    """
    sql = """
    INSERT INTO bronze.audit_log
        (run_id, source_name, execution_date, row_count, file_size_bytes,
         column_names, column_dtypes, row_hash, status, error_message, parquet_path)
    VALUES
        (%(run_id)s, %(source_name)s, %(execution_date)s, %(row_count)s,
         %(file_size_bytes)s, %(column_names)s, %(column_dtypes)s,
         %(row_hash)s, %(status)s, %(error_message)s, %(parquet_path)s)
    ON CONFLICT DO NOTHING;
    """
    with conn.cursor() as cur:
        cur.execute(sql, {
            **row,
            "column_names":  json.dumps(row.get("column_names")),
            "column_dtypes": json.dumps(row.get("column_dtypes")),
        })
    conn.commit()


def _upsert_schema_snapshot(conn, source_name: str, df: pd.DataFrame, execution_date: datetime) -> None:
    """
    Record a schema snapshot. If today's schema differs from yesterday's,
    a new row is inserted — giving you a full schema evolution history.
    """
    col_names  = df.columns.tolist()
    col_dtypes = {c: str(df[c].dtype) for c in col_names}
    schema_hash = hashlib.sha256(json.dumps(col_dtypes, sort_keys=True).encode()).hexdigest()[:16]

    sql = """
    INSERT INTO bronze.schema_snapshot
        (source_name, snapshot_date, column_names, column_dtypes, schema_hash)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (source_name, snapshot_date) DO UPDATE
        SET column_names  = EXCLUDED.column_names,
            column_dtypes = EXCLUDED.column_dtypes,
            schema_hash   = EXCLUDED.schema_hash;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (
            source_name,
            execution_date.date(),
            json.dumps(col_names),
            json.dumps(col_dtypes),
            schema_hash,
        ))
    conn.commit()
    log.info("Schema snapshot recorded for %s (hash=%s)", source_name, schema_hash)


# ---------------------------------------------------------------------------
# Core task function
# ---------------------------------------------------------------------------

def ingest_source(source_name: str, **context) -> None:
    """
    PythonOperator callable for a single source.

    Steps:
      1. Read CSV from RAW_DATA_DIR
      2. Add a bronze_ingested_at timestamp column
      3. Write partitioned Parquet to BRONZE_DIR
      4. Upsert audit_log row
      5. Upsert schema_snapshot row
      6. Update audit_log status to 'success' or 'failed'
    """
    execution_date: datetime = context["execution_date"]
    run_id: str              = context["run_id"]

    csv_path = RAW_DATA_DIR / SOURCES[source_name]
    conn     = _get_pg_conn()

    # Initialise schema on first run (idempotent)
    _ensure_audit_schema(conn)

    # --- Pre-insert a 'running' audit row so failures are still recorded ---
    audit_row = {
        "run_id":          run_id,
        "source_name":     source_name,
        "execution_date":  execution_date.date(),
        "row_count":       None,
        "file_size_bytes": None,
        "column_names":    None,
        "column_dtypes":   None,
        "row_hash":        None,
        "status":          "running",
        "error_message":   None,
        "parquet_path":    None,
    }
    _upsert_audit_row(conn, audit_row)

    try:
        # 1. Read
        log.info("Reading source: %s", csv_path)
        if not csv_path.exists():
            raise FileNotFoundError(f"Source file not found: {csv_path}")

        df = pd.read_csv(csv_path, low_memory=False)
        log.info("Loaded %d rows, %d columns from %s", len(df), len(df.columns), source_name)

        # 2. Add metadata column (do NOT transform data in Bronze)
        df["_bronze_ingested_at"]   = datetime.utcnow().isoformat()
        df["_bronze_source_file"]   = str(csv_path)
        df["_bronze_execution_date"] = execution_date.date().isoformat()

        # 3. Write Parquet
        parquet_path = _write_parquet(df, source_name, execution_date)

        # 4. Schema snapshot
        _upsert_schema_snapshot(conn, source_name, df, execution_date)

        # 5. Update audit row to 'success'
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE bronze.audit_log
                SET    status          = 'success',
                       row_count       = %s,
                       file_size_bytes = %s,
                       column_names    = %s,
                       column_dtypes   = %s,
                       row_hash        = %s,
                       parquet_path    = %s
                WHERE  run_id = %s AND source_name = %s
                """,
                (
                    len(df),
                    parquet_path.stat().st_size,
                    json.dumps(df.columns.tolist()),
                    json.dumps({c: str(df[c].dtype) for c in df.columns}),
                    _compute_df_hash(df),
                    str(parquet_path),
                    run_id,
                    source_name,
                ),
            )
        conn.commit()
        log.info("Ingestion complete for %s", source_name)

    except Exception as exc:
        log.exception("Ingestion failed for %s: %s", source_name, exc)
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE bronze.audit_log
                SET status = 'failed', error_message = %s
                WHERE run_id = %s AND source_name = %s
                """,
                (str(exc), run_id, source_name),
            )
        conn.commit()
        raise   # re-raise so Airflow marks the task as failed

    finally:
        conn.close()


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------

default_args = {
    "owner":            "risklake",
    "depends_on_past":  False,
    "email_on_failure": False,
    "email_on_retry":   False,
    "retries":          2,
    "retry_delay":      timedelta(minutes=5),
}

with DAG(
    dag_id="bronze_ingest",
    description="RiskLake — ingest raw CSV sources into partitioned Bronze Parquet store",
    default_args=default_args,
    start_date=days_ago(1),
    schedule_interval="0 1 * * *",   # 01:00 UTC daily
    catchup=False,
    max_active_runs=1,
    tags=["risklake", "bronze", "ingestion"],
) as dag:

    # One task per source — they run in parallel by default.
    # If a source depends on another, add task >> task dependencies below.
    tasks = {}
    for source_name in SOURCES:
        tasks[source_name] = PythonOperator(
            task_id=f"ingest_{source_name}",
            python_callable=ingest_source,
            op_kwargs={"source_name": source_name},
            # Airflow passes execution_date and run_id via **context
        )

    # Dependency example (uncomment if credit_bureau must load after loans):
    # tasks["loan_applications"] >> tasks["credit_bureau"]

    # All four tasks are independent — Airflow runs them in parallel.
