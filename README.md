# RiskLake — Credit Risk Intelligence Platform

> A production-grade \*\*credit risk data lakehouse\*\* built on the \*\*Bronze → Silver → Gold medallion architecture\*\* — combining Apache Airflow, dbt, scikit-learn, SHAP, ChromaDB, and Groq LLM into a complete Data Engineering + ML + AI platform.

[!\[CI](https://github.com/randeepraj2003/risklake/actions/workflows/ci.yml/badge.svg)](https://github.com/randeepraj2003/risklake/actions)
!\[Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python\&logoColor=white)
!\[PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql\&logoColor=white)
!\[dbt](https://img.shields.io/badge/dbt-1.8-FF694B?logo=dbt\&logoColor=white)
!\[Airflow](https://img.shields.io/badge/Airflow-2.9-017CEE?logo=apacheairflow\&logoColor=white)
!\[FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi\&logoColor=white)
!\[React](https://img.shields.io/badge/React-18-61DAFB?logo=react\&logoColor=black)

\---

## What is RiskLake?

RiskLake answers one question every bank needs to answer daily:

> \*\*"Should we approve this loan — and why?"\*\*

It ingests raw loan application and credit bureau data, transforms it through a three-layer medallion lakehouse, trains an ensemble ML model to predict default probability, and exposes an AI credit analyst that explains decisions in plain English using actual RBI and Basel III policy documents.

**The full pipeline — data ingestion to scored predictions — runs end to end in 14 seconds.**

\---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                            DATA SOURCES                                  │
│  Loan Applications · Credit Bureau · Transaction History · Macro Data    │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │
                    Airflow DAGs / run\_pipeline.py
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  ██████  BRONZE LAYER  — Raw Ingest                                      │
│                                                                          │
│  • CSV → partitioned Parquet (year/month/day)                            │
│  • Audit log: row count, file size, schema snapshot per run              │
│  • Schema drift detection: content hash comparison across runs           │
│  • PostgreSQL bronze schema: loan\_applications, credit\_bureau,           │
│    transactions, macro\_indicators                                         │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │
                    dbt run --select tag:silver
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  ████████  SILVER LAYER  — Clean + Feature Engineer                      │
│                                                                          │
│  stg\_loans          — type casting, null handling, deduplication         │
│  stg\_credit         — utilisation bands, inquiry velocity, age bands     │
│  feat\_dti\_ratio     — DTI calculation, LTI ratio, collateral coverage    │
│  feat\_credit\_util   — EMI regularity, spend velocity, balance trend      │
│                                                                          │
│  • dbt schema tests on every model (unique, not\_null, accepted\_values)   │
│  • dbt docs generate — serves as live data catalogue                     │
│  • PostgreSQL silver\_silver schema                                        │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │
                    train\_versioned.py --promote
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  ██████████████  GOLD LAYER  — ML + AI + Serving                         │
│                                                                          │
│  ML Engine                                                               │
│  • Random Forest + Logistic Regression ensemble (AUC 0.9993)            │
│  • Time-ordered 80/20 train/test split — no temporal leakage             │
│  • SHAP TreeExplainer — top-10 feature drivers per application           │
│  • A/B model versioning with AUC-based promotion                        │
│  • KS drift detection comparing live vs baseline PD distribution        │
│                                                                          │
│  AI Engine                                                               │
│  • ChromaDB vector store (cosine similarity, all-MiniLM-L6-v2)          │
│  • RAG pipeline grounded in RBI Master Circulars + Basel III             │
│  • Groq LLM (llama-3.1-8b-instant) — policy-cited answers               │
│                                                                          │
│  Decision Engine                                                         │
│  • Approve / Refer / Decline combining PD grade + DTI policy rules      │
│  • Aligned with RBI DTI thresholds and Basel III PD risk grades          │
│                                                                          │
│  PostgreSQL gold schema: pd\_predictions, shap\_values,                   │
│  model\_registry, model\_monitoring                                        │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │
               ┌─────────────────┴──────────────────┐
               ▼                                    ▼
       FastAPI + Redis                        React + Vite
       12 REST endpoints                      5-page dashboard
       Prometheus metrics                     Recharts visualisations
       Swagger UI                             Batch CSV upload
```

\---

## Data Engineering Stack

|Component|Technology|Purpose|
|-|-|-|
|**Orchestration**|Apache Airflow 2.9|DAG-based pipeline scheduling|
|**Transformation**|dbt 1.8|SQL-based Silver layer transforms|
|**Data Quality**|dbt tests + schema.yml|Column-level validation on every model|
|**Storage**|PostgreSQL 16|Bronze / Silver / Gold schemas|
|**File Format**|Parquet + Snappy|Partitioned Bronze layer (year/month/day)|
|**Pipeline Runner**|run\_pipeline.py|Full Bronze→Silver→Gold in 14 seconds|
|**Lineage**|dbt docs generate|Auto-generated data catalogue|
|**Audit**|bronze.audit\_log|Row count, schema hash, run history|

### dbt Silver Models

```sql
-- Four models, two staging + two feature
stg\_loans          → cleaned loan applications (type cast, dedup, null-safe)
stg\_credit         → cleaned bureau data + utilisation\_band + inquiry\_flag
feat\_dti\_ratio     → joins stg\_loans + stg\_credit → DTI, LTI, collateral\_coverage
feat\_credit\_util   → joins stg\_credit + transactions → EMI regularity, stress score
```

### Airflow DAGs

```
dags/
├── bronze\_ingest\_dag.py       # CSV → Parquet → audit\_log (01:00 UTC)
├── silver\_transform\_dag.py    # dbt run + test → silver\_pipeline\_runs (02:00 UTC)
├── gold\_model\_refresh\_dag.py  # retrain → AUC gate → model\_registry (03:00 UTC)
└── risklake\_pipeline.py       # master DAG chaining all three
```

\---

## Full Feature List

### Data Engineering

* **Medallion architecture** — Bronze / Silver / Gold with clear separation of concerns
* **Partitioned Parquet** — `year=YYYY/month=MM/day=DD` layout for time-travel queries
* **Audit trail** — every ingest run logged with row count, file size, schema hash
* **Schema snapshots** — column drift detected automatically across runs
* **dbt feature models** — DTI ratio, credit utilisation, EMI regularity computed in SQL
* **Data quality gates** — dbt tests block bad data before it reaches ML layer
* **Pipeline runner** — complete Bronze→Silver→Gold pipeline in **14 seconds**

### Machine Learning

* **Ensemble PD model** — Random Forest (70%) + Logistic Regression (30%)
* **SHAP explainability** — TreeExplainer, top-10 feature drivers per application
* **A/B model versioning** — every retrain versioned, AUC-based promotion only
* **KS drift detection** — Kolmogorov-Smirnov test vs baseline distribution
* **Model registry** — full version history with metrics, status, timestamps
* **Time-ordered split** — 80/20 split by application\_date to prevent leakage

### AI / LLM

* **RAG pipeline** — ChromaDB + sentence-transformers + Groq LLM
* **Policy grounding** — RBI Master Circulars, Basel III, AML typologies
* **Source citations** — every answer cites `\[Source N: document — section]`
* **Customer context injection** — SHAP scores injected into the prompt

### API \& Frontend

* **Decision engine** — Approve / Refer / Decline with reasoning + policy refs
* **Model comparison** — RF vs LR side-by-side with agreement indicator
* **Batch CSV scoring** — upload 500 applications, download scored results
* **5-page React dashboard** — Portfolio, Customer, AI Analyst, Batch, Model Registry
* **12 REST endpoints** — FastAPI with Swagger UI and Prometheus metrics

\---

## Project Structure

```
risklake/
├── backend/
│   ├── main.py                          # FastAPI app entry point
│   ├── run\_pipeline.py                  # Pipeline runner (14 seconds)
│   ├── generate\_mock\_data.py            # Mock CSV data generator
│   ├── app/
│   │   ├── routers/
│   │   │   ├── risk.py                  # 12 risk + model endpoints
│   │   │   └── analyst.py              # AI analyst endpoints
│   │   └── services/
│   │       ├── train\_versioned.py       # A/B versioned model training
│   │       ├── inference.py             # Predict + explain helpers
│   │       ├── decision\_engine.py       # Approve/Refer/Decline logic
│   │       ├── drift\_detection.py       # KS drift detection
│   │       ├── ingest\_docs.py           # ChromaDB document ingestion
│   │       └── query\_engine.py          # RAG + Groq generation
│   ├── dags/
│   │   ├── bronze\_ingest\_dag.py         # Airflow Bronze DAG
│   │   ├── silver\_transform\_dag.py      # Airflow Silver DAG
│   │   ├── gold\_model\_refresh\_dag.py    # Airflow Gold DAG
│   │   └── risklake\_pipeline.py         # Master pipeline DAG
│   └── dbt/
│       ├── dbt\_project.yml
│       └── models/silver/
│           ├── stg\_loans.sql            # Staging: loan applications
│           ├── stg\_credit.sql           # Staging: credit bureau
│           ├── feat\_dti\_ratio.sql       # Feature: DTI + LTI ratio
│           ├── feat\_credit\_util.sql     # Feature: utilisation + EMI
│           └── schema.yml               # Column-level tests
├── frontend/
│   └── src/pages/
│       ├── RiskDashboard.jsx            # Portfolio KPIs + grade chart
│       ├── CustomerProfile.jsx          # Lookup + SHAP + decision
│       ├── AICreditAnalyst.jsx          # RAG chat interface
│       ├── BatchUpload.jsx              # CSV upload + download
│       └── ModelRegistry.jsx            # A/B versioning + drift
├── .github/workflows/ci.yml             # lint + pytest + dbt test + docker build
└── docker-compose.yml
```

\---

## API Reference

|Endpoint|Method|Description|
|-|-|-|
|`/api/risk/predict/{id}`|GET|PD score + risk grade + customer context|
|`/api/risk/explain/{id}`|GET|SHAP risk drivers (top-N features)|
|`/api/risk/decide/{id}`|GET|Approve / Refer / Decline + reasoning|
|`/api/risk/portfolio`|GET|Portfolio KPIs + grade distribution + 30-day trend|
|`/api/risk/predict/batch`|POST|Score up to 100 applications (JSON)|
|`/api/risk/predict/batch-csv`|POST|Upload CSV → download scored results|
|`/api/risk/models`|GET|All model versions + AUC metrics|
|`/api/risk/models/{ver}/promote`|POST|Promote candidate to active|
|`/api/risk/monitoring/latest`|GET|Latest KS drift snapshot|
|`/api/analyst/ask`|POST|Ask AI credit analyst (RAG)|
|`/metrics`|GET|Prometheus metrics|
|`/docs`|GET|Interactive Swagger UI|

\---

## Model Performance

|Metric|Value|
|-|-|
|Random Forest AUC|0.9999|
|Logistic Regression AUC|0.9739|
|Ensemble AUC (RF 70% + LR 30%)|0.9993|
|Pipeline duration|**14 seconds**|
|Applications scored|1,000|
|Training approach|Time-ordered 80/20 split (no leakage)|
|Drift detection|KS test vs baseline distribution|

\---

## Quick Start

### Prerequisites

```
Python 3.11 · Node.js 20 · PostgreSQL 16 · Redis
```

### 1\. Clone and configure

```bash
git clone https://github.com/randeepraj2003/risklake.git
cd risklake
cp .env.example .env
# Add GROQ\_API\_KEY to .env (free at console.groq.com)
```

### 2\. Backend setup

```bash
cd backend
python -m venv venv
venv\\Scripts\\activate        # Windows
pip install -r requirements.txt
pip install fastapi uvicorn\[standard] groq scipy
```

### 3\. Database setup

```bash
psql -U postgres -d risklake -c "
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;"
```

### 4\. Run the full pipeline

```bash
python run\_pipeline.py
# Step 1: Generate mock data
# Step 2: Bronze ingest (4 tables)
# Step 3: dbt Silver run (4 models)
# Step 4: dbt Silver test
# Step 5: Train versioned model
# Step 6: Drift detection
# Pipeline complete in \~14 seconds
```

### 5\. Start API + Frontend

```bash
# Terminal 1 — FastAPI
$env:GROQ\_API\_KEY="your\_key"
uvicorn main:app --port 8000

# Terminal 2 — React
cd frontend \&\& npm install \&\& npm run dev
```

Open **http://localhost:5173**

\---

## Banking Domain Alignment

|RiskLake Feature|Real Banking Equivalent|
|-|-|
|Bronze ingest DAGs|Bank's data ingestion / landing zone team|
|dbt Silver models|Data engineering / feature engineering team|
|PD model + SHAP|Risk modelling / model validation team|
|Decision engine|Credit underwriting policy rules|
|RAG + RBI/Basel III|Compliance / regulatory reporting team|
|Drift detection|Model risk management (MRM) team|
|Model registry|Model governance / champion-challenger process|

\---

## Author

**Randeep Raj K**


[!\[GitHub](https://img.shields.io/badge/GitHub-randeepraj2003-181717?logo=github)](https://github.com/randeepraj2003)
[!\[LinkedIn](https://img.shields.io/badge/LinkedIn-Randeep\_Raj-0A66C2?logo=linkedin)](https://linkedin.com/in/randeep-raj)

\---

## Licence

MIT

