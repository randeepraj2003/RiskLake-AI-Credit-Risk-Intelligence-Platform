# RiskLake — Credit Risk Data Lakehouse

> A production-grade credit risk intelligence platform built on a **Bronze → Silver → Gold medallion architecture**, combining Apache Airflow, dbt, scikit-learn, SHAP, ChromaDB, and Gemini into a full-stack DE + ML + AI system.

[![CI](https://github.com/randeepraj2003/risklake/actions/workflows/ci.yml/badge.svg)](https://github.com/randeepraj2003/risklake/actions)
![Python](https://img.shields.io/badge/Python-3.11-blue)
![Airflow](https://img.shields.io/badge/Airflow-2.9-green)
![dbt](https://img.shields.io/badge/dbt-1.8-orange)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-teal)
![React](https://img.shields.io/badge/React-18-blue)

---

## What it does

RiskLake ingests raw loan application and credit bureau data, transforms it through a three-layer medallion lakehouse, trains a Random Forest PD (Probability of Default) model with SHAP explainability, and exposes an AI credit analyst powered by RAG (ChromaDB + Gemini) — all wired to a React dashboard.

A credit officer can:
- **View portfolio risk** — grade distribution (A–E), average PD, 30-day trend
- **Look up any application** — PD score, risk grade, SHAP bar chart explaining which features drove the score
- **Ask the AI analyst** — "Why was this customer flagged?" gets a Gemini answer grounded in RBI/Basel III policy with source citations

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          DATA SOURCES                               │
│   Loan Applications CSV · Credit Bureau API · Transactions CSV      │
│                         Macro Indicators API                        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  Airflow bronze_ingest DAG (01:00 UTC)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  BRONZE LAYER  — Raw Parquet (partitioned by date)                  │
│  Audit log · Schema snapshots · No transforms                       │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  Airflow silver_transform DAG (02:00 UTC)
                               │  dbt run --select tag:silver
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  SILVER LAYER  — PostgreSQL (schema: silver)                        │
│  stg_loans · stg_credit · feat_dti_ratio · feat_credit_util         │
│  Great Expectations quality checks · dbt docs data catalogue        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  Airflow gold_model_refresh DAG (03:00 UTC)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  GOLD LAYER  — ML + AI (schema: gold)                               │
│  Random Forest + Logistic Regression PD model (AUC ~0.83)          │
│  SHAP values per application · ARIMA utilisation forecast           │
│  RAG pipeline: ChromaDB + sentence-transformers + Gemini 1.5 Flash  │
│  Model registry · Pipeline run audit trail                          │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                    ┌──────────┴──────────┐
                    ▼                     ▼
            FastAPI + Redis         React + Vite
            /api/risk/*             Portfolio Dashboard
            /api/analyst/*         Customer Profile + SHAP
            Prometheus metrics      AI Analyst chat
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Orchestration | Apache Airflow 2.9 |
| Transformation | dbt 1.8 + Great Expectations |
| Storage | PostgreSQL 16 · Parquet (pyarrow + snappy) |
| ML | scikit-learn · Random Forest · Logistic Regression · ARIMA |
| Explainability | SHAP (TreeExplainer) |
| Vector DB | ChromaDB (cosine similarity) |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` |
| LLM | Gemini 1.5 Flash (Google AI) |
| API | FastAPI 0.111 · Redis (response cache) · Prometheus |
| Frontend | React 18 · Vite · Recharts |
| CI/CD | GitHub Actions (lint → pytest → dbt test → docker build) |
| Containerisation | Docker Compose |

---

## Project structure

```
risklake/
├── data/
│   ├── raw/              # Bronze source CSVs
│   └── bronze/           # Partitioned Parquet output
│       └── loan_applications/year=2024/month=01/day=01/
├── dags/
│   ├── bronze_ingest.py      # Airflow DAG — raw ingestion
│   ├── silver_transform.py   # Airflow DAG — dbt Silver run
│   └── gold_model_refresh.py # Airflow DAG — nightly ML retrain
├── dbt/
│   ├── models/
│   │   ├── bronze/           # source declarations
│   │   └── silver/           # stg_loans · stg_credit · feat_dti_ratio · feat_credit_util
│   └── dbt_project.yml
├── ml/
│   ├── train_pd_model.py     # RF + LR ensemble + SHAP → gold.pd_predictions
│   ├── inference.py          # predict() + explain() used by FastAPI
│   └── models/               # saved .pkl artefacts (git-ignored)
├── rag/
│   ├── docs/                 # RBI, Basel III, AML, product policy docs
│   ├── ingest_docs.py        # chunk + embed → ChromaDB
│   └── query_engine.py       # retrieval + Gemini generation
├── api/
│   ├── main.py               # FastAPI app + CORS + Prometheus
│   └── routers/
│       ├── risk.py           # /predict · /explain · /portfolio · /batch
│       └── analyst.py        # /ask · /explain/{app_id}
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── RiskDashboard.jsx    # Portfolio KPIs + grade chart + trend
│       │   ├── CustomerProfile.jsx  # Application lookup + SHAP bar chart
│       │   └── AICreditAnalyst.jsx  # RAG chat interface
│       └── api/client.js           # Centralised API calls
├── monitoring/
│   └── prometheus.yml
├── scripts/
│   └── init_db.sql
├── .github/workflows/ci.yml
├── docker-compose.yml
├── Dockerfile.api
└── generate_mock_data.py
```

---

## Quick start

### Prerequisites
- Docker + Docker Compose
- Python 3.11+
- Node.js 20+
- A [Gemini API key](https://ai.google.dev) (free tier works)

### 1. Clone and configure

```bash
git clone https://github.com/randeepraj2003/risklake.git
cd risklake
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY
```

### 2. Start all services

```bash
docker compose up -d
# PostgreSQL   → localhost:5432
# Redis        → localhost:6379
# Airflow UI   → localhost:8080  (admin / admin)
# FastAPI docs → localhost:8000/docs
# React UI     → localhost:5173
# Prometheus   → localhost:9090
# Grafana      → localhost:3001  (admin / risklake)
```

### 3. Run the pipeline

```bash
# Generate mock data
python generate_mock_data.py

# Ingest ChromaDB policy docs
python rag/ingest_docs.py --reset

# Train the PD model
python ml/train_pd_model.py

# Trigger Airflow DAGs manually (or wait for schedule)
# airflow dags trigger bronze_ingest
# airflow dags trigger silver_transform
# airflow dags trigger gold_model_refresh
```

### 4. Open the dashboard

Navigate to **http://localhost:5173** — the React dashboard connects to FastAPI automatically via Vite proxy.

---

## API reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/risk/predict/{application_id}` | GET | PD score + risk grade + customer context |
| `/api/risk/explain/{application_id}` | GET | SHAP risk drivers with human-readable labels |
| `/api/risk/portfolio` | GET | Grade distribution, avg PD, 30-day trend |
| `/api/risk/predict/batch` | POST | Score up to 100 applications at once |
| `/api/risk/customer/{customer_id}` | GET | All applications for one customer |
| `/api/analyst/ask` | POST | Ask the AI credit analyst any question |
| `/api/analyst/explain/{application_id}` | POST | Full credit narrative for one application |
| `/metrics` | GET | Prometheus metrics |
| `/docs` | GET | Interactive Swagger UI |

---

## Medallion architecture — data flow

```
bronze.loan_applications  ──►  silver.stg_loans  ──►  silver.feat_dti_ratio  ──►  gold.pd_predictions
bronze.credit_bureau      ──►  silver.stg_credit ──►  silver.feat_dti_ratio       gold.shap_values
                                                  ──►  silver.feat_credit_util     gold.model_registry
bronze.transactions       ──────────────────────────►  silver.feat_credit_util
```

---

## Model performance

| Metric | Value |
|---|---|
| Random Forest AUC | ~0.83 |
| Logistic Regression AUC | ~0.79 |
| Ensemble AUC (RF 70% + LR 30%) | ~0.82 |
| Training approach | Time-ordered 80/20 split (no data leakage) |
| Explainability | SHAP TreeExplainer — top 10 features per application |
| Retrain schedule | Nightly at 03:00 UTC via Airflow |
| Validation gate | Ensemble AUC must exceed 0.70 to promote |

---

## Running tests

```bash
# Python unit tests
pip install pytest httpx pytest-asyncio
pytest api/tests/ -v

# dbt tests
cd dbt
dbt test --select tag:silver

# Full CI pipeline (mirrors GitHub Actions)
# Push to main or open a PR — CI runs automatically
```

---

## Author

**Randeep Raj**
B.Tech Computer Science (Data Science) — SCMS School of Engineering and Technology
[GitHub](https://github.com/randeepraj2003) · [LinkedIn](https://linkedin.com/in/randeep-raj)

---

## Licence

MIT
