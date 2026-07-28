"""
RiskLake — Mock Data Generator
================================
Generates realistic-looking CSV files for all four Bronze sources.
Run once before starting Airflow to seed the data/raw/ directory.

Usage:
    python generate_mock_data.py

Output:
    data/raw/loan_applications.csv   (~1 000 rows)
    data/raw/credit_bureau.csv       (~1 000 rows)
    data/raw/transactions.csv        (~5 000 rows)
    data/raw/macro_indicators.csv    (~  365 rows, last 12 months daily)
"""

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

RAW_DIR = Path("data/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

rng = np.random.default_rng(42)
CUSTOMER_IDS = [f"CUST{i:05d}" for i in range(1, 1001)]


# ── 1. Loan applications ────────────────────────────────────────────────────

def gen_loan_applications(n: int = 1000) -> pd.DataFrame:
    employment_types = ["salaried", "self_employed", "contract", "unemployed"]
    purposes         = ["home_purchase", "refinance", "auto", "personal", "business"]

    annual_income = rng.integers(200_000, 2_000_000, size=n)   # INR
    loan_amount   = (annual_income * rng.uniform(0.5, 5.0, size=n)).astype(int)
    credit_score  = rng.integers(300, 900, size=n)

    # Simple rule-based default label (not a real model — Silver/Gold will score properly)
    default = (
        (credit_score < 550).astype(int)
        | (loan_amount / annual_income > 4).astype(int)
    ).clip(0, 1)

    return pd.DataFrame({
        "application_id":    [f"APP{i:06d}" for i in range(1, n + 1)],
        "customer_id":       rng.choice(CUSTOMER_IDS, size=n, replace=False),
        "application_date":  pd.date_range("2023-01-01", periods=n, freq="8h").date,
        "loan_amount_inr":   loan_amount,
        "loan_term_months":  rng.choice([12, 24, 36, 60, 84, 120], size=n),
        "annual_income_inr": annual_income,
        "employment_type":   rng.choice(employment_types, size=n),
        "loan_purpose":      rng.choice(purposes, size=n),
        "existing_loans":    rng.integers(0, 6, size=n),
        "credit_score":      credit_score,
        "collateral_value":  rng.integers(0, 5_000_000, size=n),
        "default_flag":      default,            # 1 = historical default
    })


# ── 2. Credit bureau ────────────────────────────────────────────────────────

def gen_credit_bureau(n: int = 1000) -> pd.DataFrame:
    return pd.DataFrame({
        "customer_id":            rng.choice(CUSTOMER_IDS, size=n, replace=False),
        "bureau_pull_date":       pd.date_range("2024-01-01", periods=n, freq="6h").date,
        "credit_score":           rng.integers(300, 900, size=n),
        "total_accounts":         rng.integers(1, 20, size=n),
        "open_accounts":          rng.integers(0, 10, size=n),
        "delinquent_accounts":    rng.integers(0, 5,  size=n),
        "credit_utilisation_pct": rng.uniform(0, 1, size=n).round(4),
        "oldest_account_months":  rng.integers(1, 240, size=n),
        "hard_inquiries_6m":      rng.integers(0, 10, size=n),
        "total_credit_limit_inr": rng.integers(50_000, 2_000_000, size=n),
        "total_balance_inr":      rng.integers(0, 1_500_000, size=n),
    })


# ── 3. Transactions ─────────────────────────────────────────────────────────

def gen_transactions(n: int = 5000) -> pd.DataFrame:
    txn_types = ["debit", "credit", "transfer", "emi_payment", "atm_withdrawal"]
    channels  = ["mobile_app", "internet_banking", "branch", "atm", "pos"]

    start = date(2023, 1, 1)
    txn_dates = [start + timedelta(days=int(d)) for d in rng.integers(0, 365, size=n)]

    return pd.DataFrame({
        "transaction_id":   [f"TXN{i:07d}" for i in range(1, n + 1)],
        "customer_id":      rng.choice(CUSTOMER_IDS, size=n),
        "transaction_date": txn_dates,
        "amount_inr":       rng.integers(100, 500_000, size=n),
        "transaction_type": rng.choice(txn_types, size=n),
        "channel":          rng.choice(channels, size=n),
        "merchant_code":    [f"MCC{rng.integers(1000, 9999)}" for _ in range(n)],
        "balance_after_inr": rng.integers(0, 2_000_000, size=n),
        "is_flagged":       rng.choice([0, 1], size=n, p=[0.97, 0.03]),
    })


# ── 4. Macro indicators ──────────────────────────────────────────────────────

def gen_macro_indicators() -> pd.DataFrame:
    days = pd.date_range("2023-01-01", "2024-01-01", freq="D")
    n    = len(days)

    # Simulate slowly drifting macro series
    repo_rate     = 6.50 + np.cumsum(rng.normal(0, 0.01, n))
    cpi           = 5.50 + np.cumsum(rng.normal(0, 0.02, n))
    gdp_growth    = 7.00 + np.cumsum(rng.normal(0, 0.03, n))
    unemployment  = 7.50 + np.cumsum(rng.normal(0, 0.02, n))
    usd_inr       = 83.0 + np.cumsum(rng.normal(0, 0.05, n))

    return pd.DataFrame({
        "date":                  days.date,
        "rbi_repo_rate_pct":     repo_rate.round(2),
        "cpi_inflation_pct":     cpi.round(2),
        "gdp_growth_rate_pct":   gdp_growth.round(2),
        "unemployment_rate_pct": unemployment.round(2),
        "usd_inr_exchange":      usd_inr.round(2),
        "nifty_50_index":        (15000 + np.cumsum(rng.normal(10, 80, n))).round(0).astype(int),
    })


if __name__ == "__main__":
    print("Generating mock data...")

    df_loans = gen_loan_applications()
    df_loans.to_csv(RAW_DIR / "loan_applications.csv", index=False)
    print(f"  loan_applications.csv  — {len(df_loans):,} rows")

    df_bureau = gen_credit_bureau()
    df_bureau.to_csv(RAW_DIR / "credit_bureau.csv", index=False)
    print(f"  credit_bureau.csv      — {len(df_bureau):,} rows")

    df_txn = gen_transactions()
    df_txn.to_csv(RAW_DIR / "transactions.csv", index=False)
    print(f"  transactions.csv       — {len(df_txn):,} rows")

    df_macro = gen_macro_indicators()
    df_macro.to_csv(RAW_DIR / "macro_indicators.csv", index=False)
    print(f"  macro_indicators.csv   — {len(df_macro):,} rows")

    print("\nDone. Files written to data/raw/")
