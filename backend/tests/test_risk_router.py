"""
RiskLake — API Tests
File   : api/tests/test_risk_router.py

Unit + integration tests for /risk/* endpoints.
Uses pytest + httpx TestClient. Mocks Redis and inference layer
so tests run without a live PostgreSQL or Redis instance.

Run:
    pip install pytest httpx pytest-asyncio
    pytest api/tests/test_risk_router.py -v

Author : Randeep Raj
Project: RiskLake
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# ── Mock data ─────────────────────────────────────────────────────────────────

MOCK_DB_ROW = {
    "application_id":      "APP000001",
    "customer_id":         "CUST00001",
    "pd_probability_rf":   0.2100,
    "pd_probability_lr":   0.2450,
    "pd_probability_ens":  0.2205,
    "pd_prediction":       0,
    "risk_grade":          "C",
    "model_version":       "v20240601_0100",
    "scored_at":           "2024-06-01 03:15:00+00",
    "loan_amount_inr":     500000,
    "annual_income_inr":   1200000,
    "loan_purpose":        "personal",
    "employment_type":     "salaried",
    "dti_ratio":           0.38,
    "dti_risk_tier":       "moderate",
    "credit_risk_tier":    "medium",
    "credit_score":        680,
    "loan_to_income_ratio": 0.42,
}

MOCK_SHAP_ROWS = [
    {"rank": 1, "feature": "dti_ratio",           "shap_value":  0.18, "direction": "increases_risk", "label": "Strongly — High Debt-to-Income ratio increases default risk",      "model_version": "v20240601_0100"},
    {"rank": 2, "feature": "credit_stress_score", "shap_value":  0.12, "direction": "increases_risk", "label": "Moderately — High Credit stress score increases default risk",     "model_version": "v20240601_0100"},
    {"rank": 3, "feature": "emi_regularity_score","shap_value": -0.09, "direction": "decreases_risk", "label": "Moderately — Good EMI payment regularity reduces default risk",    "model_version": "v20240601_0100"},
    {"rank": 4, "feature": "credit_score",         "shap_value": -0.07, "direction": "decreases_risk", "label": "Slightly — Good Credit score (CIBIL) reduces default risk",       "model_version": "v20240601_0100"},
    {"rank": 5, "feature": "hard_inquiries_6m",   "shap_value":  0.04, "direction": "increases_risk", "label": "Slightly — High Hard credit inquiries (6 months) increases default risk", "model_version": "v20240601_0100"},
]

MOCK_PORTFOLIO = {
    "total_applications": 1000,
    "high_risk_count":    120,
    "high_risk_pct":      12.0,
    "portfolio_avg_pd":   0.1850,
    "grade_distribution": [
        {"risk_grade": "A", "count": 310, "avg_pd": 0.032, "min_pd": 0.01, "max_pd": 0.049},
        {"risk_grade": "B", "count": 290, "avg_pd": 0.095, "min_pd": 0.05, "max_pd": 0.149},
        {"risk_grade": "C", "count": 280, "avg_pd": 0.213, "min_pd": 0.15, "max_pd": 0.299},
        {"risk_grade": "D", "count": 95,  "avg_pd": 0.381, "min_pd": 0.30, "max_pd": 0.499},
        {"risk_grade": "E", "count": 25,  "avg_pd": 0.721, "min_pd": 0.50, "max_pd": 0.980},
    ],
    "pd_trend_30d": [
        {"date": "2024-05-01", "avg_pd": 0.182, "scored_count": 30},
        {"date": "2024-05-02", "avg_pd": 0.189, "scored_count": 32},
    ],
}


# ── App fixture ───────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """TestClient with all external dependencies mocked."""
    with (
        patch("api.routers.risk._cache_get",  return_value=None),
        patch("api.routers.risk._cache_set",  return_value=None),
        patch("api.routers.risk._fetch_prediction_from_db", return_value=MOCK_DB_ROW),
        patch("api.routers.risk._fetch_shap_from_db",       return_value=MOCK_SHAP_ROWS),
        patch("api.routers.risk._fetch_portfolio_summary",  return_value=MOCK_PORTFOLIO),
    ):
        from api.main import app
        with TestClient(app) as c:
            yield c


# ── /predict tests ────────────────────────────────────────────────────────────

class TestPredict:

    def test_predict_returns_200(self, client):
        r = client.get("/api/risk/predict/APP000001")
        assert r.status_code == 200

    def test_predict_response_schema(self, client):
        data = client.get("/api/risk/predict/APP000001").json()
        assert data["application_id"]     == "APP000001"
        assert data["customer_id"]        == "CUST00001"
        assert data["risk_grade"]         == "C"
        assert data["pd_prediction"]      == 0
        assert 0 <= data["pd_probability_ens"] <= 1
        assert 0 <= data["pd_probability_rf"]  <= 1
        assert 0 <= data["pd_probability_lr"]  <= 1

    def test_predict_contains_model_version(self, client):
        data = client.get("/api/risk/predict/APP000001").json()
        assert data["model_version"] == "v20240601_0100"

    def test_predict_contains_silver_context(self, client):
        data = client.get("/api/risk/predict/APP000001").json()
        assert data["dti_ratio"]       == pytest.approx(0.38)
        assert data["credit_score"]    == 680
        assert data["employment_type"] == "salaried"
        assert data["loan_purpose"]    == "personal"

    def test_predict_latency_field_present(self, client):
        data = client.get("/api/risk/predict/APP000001").json()
        assert "latency_ms" in data
        assert isinstance(data["latency_ms"], float)

    def test_predict_404_on_unknown_application(self, client):
        with (
            patch("api.routers.risk._fetch_prediction_from_db", return_value=None),
            patch("api.routers.risk.ml_predict",
                  side_effect=ValueError("not found")),
        ):
            r = client.get("/api/risk/predict/NOTEXIST999")
            assert r.status_code == 404
            assert "not found" in r.json()["detail"].lower()

    def test_predict_cache_hit_flag(self, client):
        """Cache hit path returns cache_hit=True."""
        cached = {**MOCK_DB_ROW, "cache_hit": True, "latency_ms": 0.5}
        with patch("api.routers.risk._cache_get", return_value=cached):
            data = client.get("/api/risk/predict/APP000001").json()
            assert data["cache_hit"] is True

    def test_predict_503_when_model_not_loaded(self, client):
        with (
            patch("api.routers.risk._fetch_prediction_from_db", return_value=None),
            patch("api.routers.risk.ml_predict",
                  side_effect=RuntimeError("Models not loaded")),
        ):
            r = client.get("/api/risk/predict/APP999999")
            assert r.status_code == 503

    def test_risk_grade_values(self, client):
        valid_grades = {"A", "B", "C", "D", "E"}
        data = client.get("/api/risk/predict/APP000001").json()
        assert data["risk_grade"] in valid_grades


# ── /explain tests ────────────────────────────────────────────────────────────

class TestExplain:

    def test_explain_returns_200(self, client):
        r = client.get("/api/risk/explain/APP000001")
        assert r.status_code == 200

    def test_explain_returns_risk_drivers(self, client):
        data = client.get("/api/risk/explain/APP000001").json()
        assert "risk_drivers" in data
        assert len(data["risk_drivers"]) == 5

    def test_explain_driver_schema(self, client):
        drivers = client.get("/api/risk/explain/APP000001").json()["risk_drivers"]
        first   = drivers[0]
        assert "rank"         in first
        assert "feature"      in first
        assert "shap_value"   in first
        assert "direction"    in first
        assert "label"        in first
        assert "model_version" in first

    def test_explain_direction_values(self, client):
        drivers = client.get("/api/risk/explain/APP000001").json()["risk_drivers"]
        for d in drivers:
            assert d["direction"] in ("increases_risk", "decreases_risk")

    def test_explain_ranked_by_importance(self, client):
        drivers = client.get("/api/risk/explain/APP000001").json()["risk_drivers"]
        shap_abs = [abs(d["shap_value"]) for d in drivers]
        assert shap_abs == sorted(shap_abs, reverse=True), \
            "Drivers should be sorted by |SHAP| descending"

    def test_explain_embeds_pd_summary(self, client):
        """The /explain endpoint embeds the PD context for single-call UX."""
        data = client.get("/api/risk/explain/APP000001").json()
        assert "pd_summary" in data
        if data["pd_summary"]:  # None is acceptable if DB join finds nothing
            assert "pd_probability_ens" in data["pd_summary"]
            assert "risk_grade"         in data["pd_summary"]

    def test_explain_top_n_param(self, client):
        r = client.get("/api/risk/explain/APP000001?top_n=3")
        assert r.status_code == 200

    def test_explain_top_n_max_20(self, client):
        r = client.get("/api/risk/explain/APP000001?top_n=25")
        assert r.status_code == 422   # Pydantic validation error

    def test_explain_404_when_no_shap(self, client):
        with (
            patch("api.routers.risk._fetch_shap_from_db", return_value=[]),
            patch("api.routers.risk.ml_explain",
                  side_effect=Exception("no SHAP values")),
        ):
            r = client.get("/api/risk/explain/NOSHAP999")
            assert r.status_code == 404

    def test_explain_label_is_human_readable(self, client):
        drivers = client.get("/api/risk/explain/APP000001").json()["risk_drivers"]
        for d in drivers:
            assert len(d["label"]) > 10, "Label should be a meaningful sentence"
            assert d["label"][0].isupper(), "Label should start with a capital letter"


# ── /portfolio tests ──────────────────────────────────────────────────────────

class TestPortfolio:

    def test_portfolio_returns_200(self, client):
        r = client.get("/api/risk/portfolio")
        assert r.status_code == 200

    def test_portfolio_schema(self, client):
        data = client.get("/api/risk/portfolio").json()
        assert data["total_applications"] == 1000
        assert data["high_risk_count"]    == 120
        assert data["high_risk_pct"]      == pytest.approx(12.0)
        assert 0 < data["portfolio_avg_pd"] < 1
        assert len(data["grade_distribution"]) == 5
        assert len(data["pd_trend_30d"])       == 2

    def test_portfolio_grade_distribution_keys(self, client):
        grades = client.get("/api/risk/portfolio").json()["grade_distribution"]
        for g in grades:
            assert "risk_grade" in g
            assert "count"      in g
            assert "avg_pd"     in g


# ── /predict/batch tests ──────────────────────────────────────────────────────

class TestBatchPredict:

    def test_batch_returns_200(self, client):
        r = client.post("/api/risk/predict/batch",
                        json={"application_ids": ["APP000001", "APP000002"]})
        assert r.status_code == 200

    def test_batch_results_count(self, client):
        ids  = ["APP000001", "APP000002", "APP000003"]
        data = client.post("/api/risk/predict/batch",
                           json={"application_ids": ids}).json()
        assert data["total"] == len(ids)
        assert len(data["results"]) == len(ids)

    def test_batch_partial_failure_isolated(self, client):
        """One failing ID should not fail the whole batch."""
        call_count = {"n": 0}

        def mock_fetch(app_id):
            call_count["n"] += 1
            if app_id == "APP_BAD":
                return None
            return MOCK_DB_ROW

        def mock_live(app_id):
            if app_id == "APP_BAD":
                raise ValueError("not found")
            return MOCK_DB_ROW

        with (
            patch("api.routers.risk._fetch_prediction_from_db", side_effect=mock_fetch),
            patch("api.routers.risk.ml_predict", side_effect=mock_live),
        ):
            data = client.post("/api/risk/predict/batch",
                               json={"application_ids": ["APP000001", "APP_BAD"]}).json()
        assert data["total"]        == 1
        assert len(data["errors"])  == 1
        assert data["errors"][0]["application_id"] == "APP_BAD"

    def test_batch_rejects_over_100_ids(self, client):
        ids = [f"APP{i:06d}" for i in range(101)]
        r   = client.post("/api/risk/predict/batch", json={"application_ids": ids})
        assert r.status_code == 422


# ── /customer tests ───────────────────────────────────────────────────────────

class TestCustomer:

    def test_customer_returns_200(self, client):
        mock_apps = [
            {**MOCK_DB_ROW, "application_date": "2024-01-15",
             "risk_grade": "C", "pd_probability_ens": 0.22},
        ]
        with patch("api.routers.risk._fetch_customer_applications", return_value=mock_apps):
            r = client.get("/api/risk/customer/CUST00001")
        assert r.status_code == 200

    def test_customer_404_on_unknown(self, client):
        with patch("api.routers.risk._fetch_customer_applications", return_value=[]):
            r = client.get("/api/risk/customer/CUST99999")
        assert r.status_code == 404


# ── Health and system ─────────────────────────────────────────────────────────

class TestSystem:

    def test_root_returns_endpoint_map(self, client):
        data = client.get("/").json()
        assert "endpoints" in data
        assert "predict" in data["endpoints"]
        assert "explain" in data["endpoints"]

    def test_health_returns_ok(self, client):
        data = client.get("/health").json()
        assert data["status"] == "ok"

    def test_docs_accessible(self, client):
        r = client.get("/docs")
        assert r.status_code == 200
