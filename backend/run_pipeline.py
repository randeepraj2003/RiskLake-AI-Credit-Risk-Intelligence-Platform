"""
RiskLake - Manual Pipeline Runner v2
Run: python run_pipeline.py
"""
import logging
import os
import subprocess
import sys
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("risklake.pipeline")

BACKEND = os.path.dirname(os.path.abspath(__file__))
PYTHON  = sys.executable
DBT_DIR = os.path.join(BACKEND, "dbt")
PG_ENV  = {**os.environ,
            "PG_HOST":"localhost", "PG_PORT":"5432",
            "PG_DB":"risklake", "PG_USER":"postgres",
            "PG_PASSWORD": os.environ.get("PG_PASSWORD"), "RISKLAKE_ROOT": BACKEND}

def run(name, cmd, cwd=None):
    log.info("STEP: %s", name)
    result = subprocess.run(cmd, capture_output=True, text=True,
                            env=PG_ENV, cwd=cwd or BACKEND)
    if result.stdout:
        log.info(result.stdout[-800:])
    if result.returncode != 0:
        log.error("FAILED: %s\n%s", name, result.stderr[-800:])
        raise RuntimeError(f"{name} failed")
    log.info("DONE: %s\n", name)


def bronze_ingest():
    log.info("STEP: 2. Bronze ingest")

    import pandas as pd
    import psycopg2
    from psycopg2.extras import execute_values

    conn = psycopg2.connect(
        host="localhost", dbname="risklake",
        user="postgres", password="risklake"
    )

    for tbl in ["loan_applications","credit_bureau","transactions","macro_indicators"]:
        csv_path = os.path.join(BACKEND, "data", "raw", f"{tbl}.csv")
        df = pd.read_csv(csv_path)

        # Drop table and recreate
        with conn.cursor() as cur:
            cur.execute(f'DROP TABLE IF EXISTS bronze."{tbl}"')
            # Build CREATE TABLE from DataFrame dtypes
            cols = []
            for col, dtype in df.dtypes.items():
                if "int" in str(dtype):
                    pg_type = "BIGINT"
                elif "float" in str(dtype):
                    pg_type = "FLOAT"
                else:
                    pg_type = "TEXT"
                cols.append(f'"{col}" {pg_type}')
            cur.execute(f'CREATE TABLE IF NOT EXISTS bronze."{tbl}" ({", ".join(cols)})')

            # Insert rows in batches
            df = df.astype(object).where(pd.notna(df), None)
            rows = [tuple(r) for r in df.itertuples(index=False)]
            col_names = ", ".join(f'"{c}"' for c in df.columns)
            sql = f'INSERT INTO bronze."{tbl}" ({col_names}) VALUES %s'
            execute_values(cur, sql, rows, page_size=500)

        conn.commit()
        log.info("  Loaded %s: %d rows", tbl, len(df))

    conn.close()
    log.info("DONE: 2. Bronze ingest\n")


if __name__ == "__main__":
    start = datetime.now()
    log.info("=" * 55)
    log.info("RiskLake Pipeline Started: %s", start.strftime("%Y-%m-%d %H:%M"))
    log.info("=" * 55)

    run("1. Generate mock data", [PYTHON, "generate_mock_data.py"])
    bronze_ingest()
    run("3. dbt Silver run",  ["dbt", "run",  "--select", "tag:silver"], cwd=DBT_DIR)
    run("4. dbt Silver test", ["dbt", "test", "--select", "tag:silver"], cwd=DBT_DIR)
    run("5. Train versioned model",
        [PYTHON, os.path.join("app","services","train_versioned.py"), "--promote"])
    run("6. Drift detection",
        [PYTHON, os.path.join("app","services","drift_detection.py")])

    end = datetime.now()
    log.info("=" * 55)
    log.info("Pipeline complete! Duration: %s", end - start)
    log.info("=" * 55)
