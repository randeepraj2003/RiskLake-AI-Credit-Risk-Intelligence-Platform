"""
RiskLake — SHAP Explain Utility
================================
Loaded by the FastAPI /explain endpoint at startup.
Provides instant per-customer SHAP waterfall explanations from
pre-trained artefacts — no retraining required at inference time.

Usage (from FastAPI router)
---------------------------
    from ml.explain_shap import SHAPExplainer
    explainer = SHAPExplainer()                     # loads artefacts once
    result    = explainer.explain("APP000042", row_df)

Returns
-------
{
    "application_id": "APP000042",
    "pd_score":        0.73,
    "pd_label":        "HIGH",
    "base_value":      0.18,
    "top_drivers": [
        {"feature": "dti_ratio",           "shap_value": 0.21,  "feature_value": 0.61, "direction": "increases_risk"},
        {"feature": "credit_stress_score", "shap_value": 0.15,  "feature_value": 3,    "direction": "increases_risk"},
        {"feature": "emi_regularity_score","shap_value": -0.09, "feature_value": 0.83, "direction": "reduces_risk"},
        ...
    ],
    "narrative_context": "Customer has high DTI (0.61) and elevated credit stress..."
}

Author : Randeep Raj
Project: RiskLake
"""

from __future__ import annotations

import json
import logging
import os
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(os.environ.get("RISKLAKE_ROOT", Path(__file__).resolve().parents[1]))
PROD_DIR     = PROJECT_ROOT / "ml" / "models" / "production"


class SHAPExplainer:
    """
    Singleton-style wrapper loaded once at FastAPI startup.
    Call explain() per request — zero reloading overhead.
    """

    def __init__(self, model_dir: Path = PROD_DIR) -> None:
        self.model_dir    = model_dir
        self._rf          = None
        self._explainer   = None
        self._lr_pipeline = None
        self._feature_cols: list[str] = []
        self._load()

    def _load(self) -> None:
        """Load all artefacts from the production model directory."""
        try:
            with open(self.model_dir / "rf_pd_model.pkl",  "rb") as f:
                self._rf = pickle.load(f)
            with open(self.model_dir / "lr_pd_model.pkl",  "rb") as f:
                self._lr_pipeline = pickle.load(f)
            with open(self.model_dir / "shap_explainer.pkl","rb") as f:
                self._explainer = pickle.load(f)
            with open(self.model_dir / "feature_columns.json") as f:
                self._feature_cols = json.load(f)

            log.info("SHAPExplainer loaded %d features from %s",
                     len(self._feature_cols), self.model_dir)
        except FileNotFoundError as exc:
            log.error("Model artefacts not found at %s. Run train_pd_model.py first. (%s)",
                      self.model_dir, exc)
            raise

    def _ensemble_score(self, X: np.ndarray) -> float:
        """Weighted ensemble PD score for a single row."""
        lr_p = self._lr_pipeline.predict_proba(X)[0, 1]
        rf_p = self._rf.predict_proba(X)[0, 1]
        return float(0.30 * lr_p + 0.70 * rf_p)

    def _pd_label(self, score: float) -> str:
        if score >= 0.70:  return "VERY HIGH"
        if score >= 0.50:  return "HIGH"
        if score >= 0.30:  return "MEDIUM"
        return "LOW"

    def _build_narrative_context(self, drivers: list[dict]) -> str:
        """
        Build a 2-sentence plain-English context string for the RAG prompt.
        The AI credit analyst prepends this to its retrieval context so the
        LLM always has the top risk drivers grounded in actual SHAP data.
        """
        top_risk    = [d for d in drivers if d["direction"] == "increases_risk"][:3]
        top_protect = [d for d in drivers if d["direction"] == "reduces_risk"][:2]

        risk_parts = ", ".join(
            f"{d['feature'].replace('_', ' ')} ({d['feature_value']})"
            for d in top_risk
        ) or "no dominant risk factors"

        protect_parts = ", ".join(
            f"{d['feature'].replace('_', ' ')} ({d['feature_value']})"
            for d in top_protect
        ) or "no significant protective factors"

        return (
            f"The primary factors increasing default risk are: {risk_parts}. "
            f"Protective factors include: {protect_parts}."
        )

    def align_row(self, row: dict | pd.DataFrame) -> pd.DataFrame:
        """
        Align an arbitrary input dict/DataFrame to the exact feature column
        order the model was trained on. Missing columns default to 0.
        """
        if isinstance(row, dict):
            row = pd.DataFrame([row])
        aligned = pd.DataFrame(0, index=row.index, columns=self._feature_cols)
        for col in self._feature_cols:
            if col in row.columns:
                aligned[col] = row[col].values
        return aligned

    def explain(self, application_id: str, row: dict | pd.DataFrame) -> dict:
        """
        Main entry point for FastAPI /explain endpoint.

        Parameters
        ----------
        application_id : unique loan application ID
        row            : dict or 1-row DataFrame of raw feature values

        Returns
        -------
        Full explanation dict (see module docstring).
        """
        X = self.align_row(row)

        # PD score
        pd_score = self._ensemble_score(X.values)

        # SHAP values for this customer
        sv = self._explainer.shap_values(X)
        if isinstance(sv, list):
            sv = sv[1]
        sv_flat = sv[0]

        # Base value
        base_val = self._explainer.expected_value
        if isinstance(base_val, (list, np.ndarray)):
            base_val = base_val[1]

        # Build driver list
        drivers = []
        for i, col in enumerate(self._feature_cols):
            shap_val = float(sv_flat[i])
            if abs(shap_val) < 1e-6:
                continue
            drivers.append({
                "feature":       col,
                "shap_value":    round(shap_val, 5),
                "feature_value": round(float(X.iloc[0, i]), 4),
                "direction":     "increases_risk" if shap_val > 0 else "reduces_risk",
            })

        drivers.sort(key=lambda d: abs(d["shap_value"]), reverse=True)
        top_10 = drivers[:10]

        return {
            "application_id":    application_id,
            "pd_score":          round(pd_score, 4),
            "pd_label":          self._pd_label(pd_score),
            "base_value":        round(float(base_val), 5),
            "top_drivers":       top_10,
            "narrative_context": self._build_narrative_context(top_10),
        }
