"""
RiskLake - Versioned Model Training
File: backend/app/services/train_versioned.py

Run: python app/services/train_versioned.py
     python app/services/train_versioned.py --promote
"""
from __future__ import annotations
import argparse, json, logging, os, pickle
from datetime import datetime
from pathlib import Path
import pandas as pd
import psycopg2
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, average_precision_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("risklake.train_versioned")

PROJECT_ROOT = Path(os.environ.get("RISKLAKE_ROOT", Path(__file__).resolve().parents[2]))
MODELS_DIR   = PROJECT_ROOT / "ml" / "models"
PG_CONN = {
    "host":     os.environ.get("PG_HOST",     "localhost"),
    "dbname":   os.environ.get("PG_DB",       "risklake"),
    "user":     os.environ.get("PG_USER",     "postgres"),
    "password": os.environ.get("PG_PASSWORD", "risklake"),
}
NUM_COLS = ["annual_income_inr","loan_amount_inr","loan_term_months","credit_score",
            "loan_to_income_ratio","collateral_coverage_ratio","bureau_utilisation_pct",
            "emi_regularity_score","credit_stress_score"]
CAT_COLS = ["employment_type","loan_purpose","credit_risk_tier"]
TARGET   = "default_flag"

def get_conn(): return psycopg2.connect(**PG_CONN)

def load_data():
    conn = get_conn()
    df = pd.read_sql("""
        SELECT d.application_id, d.customer_id, d.application_date,
               d.annual_income_inr, d.loan_amount_inr, d.loan_term_months,
               d.employment_type, d.loan_purpose, d.credit_score,
               d.loan_to_income_ratio, d.collateral_coverage_ratio,
               d.credit_risk_tier, d.default_flag,
               COALESCE(u.bureau_utilisation_pct,0) AS bureau_utilisation_pct,
               COALESCE(u.emi_regularity_score,0)   AS emi_regularity_score,
               COALESCE(u.credit_stress_score,0)    AS credit_stress_score
        FROM silver_silver.feat_dti_ratio d
        LEFT JOIN silver_silver.feat_credit_util u USING (customer_id)
        WHERE d.default_flag IS NOT NULL
    """, conn)
    conn.close()
    log.info("Loaded %d rows. Default rate: %.2f%%", len(df), df[TARGET].mean()*100)
    return df

def engineer(df):
    for c in NUM_COLS:
        if c in df.columns: df[c] = df[c].fillna(df[c].median())
    for c in CAT_COLS:
        if c in df.columns: df[c] = df[c].fillna("unknown")
    df_enc = pd.get_dummies(df, columns=CAT_COLS)
    feat_cols = [c for c in df_enc.columns if c in NUM_COLS or any(c.startswith(x+"_") for x in CAT_COLS)]
    return df_enc, feat_cols

def train(version: str, promote: bool = False) -> dict:
    log.info("Training model version: %s", version)
    df_raw = load_data()
    df, feat_cols = engineer(df_raw.copy())
    df_sorted = df.sort_values("application_date").reset_index(drop=True)
    split = int(len(df_sorted)*0.8)
    X_train, y_train = df_sorted.iloc[:split][feat_cols], df_sorted.iloc[:split][TARGET]
    X_test,  y_test  = df_sorted.iloc[split:][feat_cols],  df_sorted.iloc[split:][TARGET]

    rf = RandomForestClassifier(n_estimators=100, max_depth=8, class_weight="balanced", random_state=42, n_jobs=-1)
    rf.fit(X_train, y_train)
    lr = Pipeline([("scaler",StandardScaler()),("lr",LogisticRegression(class_weight="balanced",max_iter=1000,random_state=42))])
    lr.fit(X_train, y_train)

    rf_prob  = rf.predict_proba(X_test)[:,1]
    lr_prob  = lr.predict_proba(X_test)[:,1]
    ens_prob = 0.7*rf_prob + 0.3*lr_prob
    rf_auc   = roc_auc_score(y_test, rf_prob)
    lr_auc   = roc_auc_score(y_test, lr_prob)
    ens_auc  = roc_auc_score(y_test, ens_prob)
    avg_prec = average_precision_score(y_test, ens_prob)
    log.info("RF AUC: %.4f | LR AUC: %.4f | Ensemble AUC: %.4f", rf_auc, lr_auc, ens_auc)

    ver_dir = MODELS_DIR / version
    ver_dir.mkdir(parents=True, exist_ok=True)
    with open(ver_dir/"rf_pd_model.pkl","wb") as f: pickle.dump(rf, f)
    with open(ver_dir/"lr_pd_model.pkl","wb") as f: pickle.dump(lr, f)
    with open(ver_dir/"feature_columns.json","w") as f: json.dump(feat_cols, f)

    status = "candidate"
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS gold.model_registry (
        id SERIAL PRIMARY KEY, model_version TEXT NOT NULL UNIQUE,
        rf_auc FLOAT, lr_auc FLOAT, ensemble_auc FLOAT, avg_precision FLOAT,
        feature_count INTEGER, train_rows INTEGER, test_rows INTEGER,
        status TEXT NOT NULL DEFAULT 'candidate',
        trained_at TIMESTAMPTZ, registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), notes TEXT
    )""")

    cur.execute("SELECT COUNT(*) FROM gold.model_registry WHERE status='active'")
    if cur.fetchone()[0] == 0:
        status = "active"
    elif promote:
        cur.execute("SELECT ensemble_auc FROM gold.model_registry WHERE status='active' ORDER BY registered_at DESC LIMIT 1")
        row = cur.fetchone()
        current_best = float(row[0]) if row else 0.0
        if ens_auc > current_best:
            cur.execute("UPDATE gold.model_registry SET status='retired' WHERE status='active'")
            status = "active"
            log.info("Promoting %s (%.4f > %.4f)", version, ens_auc, current_best)
        else:
            log.info("Not promoting — %.4f <= %.4f", ens_auc, current_best)

    cur.execute("""INSERT INTO gold.model_registry
        (model_version,rf_auc,lr_auc,ensemble_auc,avg_precision,feature_count,train_rows,test_rows,status,trained_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (model_version) DO UPDATE SET ensemble_auc=EXCLUDED.ensemble_auc,
        status=EXCLUDED.status, registered_at=NOW()""",
        (version,rf_auc,lr_auc,ens_auc,avg_prec,len(feat_cols),len(X_train),len(X_test),status,datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

    metadata = {"model_version":version,"trained_at":datetime.utcnow().isoformat(),
                "rf_auc":round(rf_auc,4),"lr_auc":round(lr_auc,4),"ensemble_auc":round(ens_auc,4),
                "avg_precision":round(avg_prec,4),"feature_count":len(feat_cols),"status":status}
    with open(ver_dir/"model_metadata.json","w") as f: json.dump(metadata, f, indent=2)
    with open(MODELS_DIR/"model_metadata.json","w") as f: json.dump(metadata, f, indent=2)

    log.info("Registered %s with status '%s'", version, status)
    return metadata

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--promote", action="store_true")
    parser.add_argument("--version", default=None)
    args    = parser.parse_args()
    version = args.version or f"v{datetime.utcnow().strftime('%Y%m%d_%H%M')}"
    result  = train(version, promote=args.promote)
    print(f"\nDone. Version={result['model_version']} | AUC={result['ensemble_auc']} | Status={result['status']}")
