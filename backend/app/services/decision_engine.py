"""
RiskLake — Decision Engine
File   : app/services/decision_engine.py

Combines the Gold-layer PD risk_grade with Silver-layer DTI/credit_score
policy rules into a structured APPROVE / REFER / DECLINE decision.

Pure function module — no DB or network calls. Caller (risk.py router)
fetches the data, this module just decides.
"""

from __future__ import annotations


def make_decision(
    risk_grade: str,
    pd_probability_ens: float,
    dti_ratio: float | None,
    dti_risk_tier: str | None,
    credit_score: float | None,
) -> dict:
    """
    Decision matrix:
      Grade A/B + DTI low/moderate          -> APPROVE
      Grade C    + DTI moderate/elevated     -> REFER
      Grade D/E OR DTI high OR credit < 550  -> DECLINE
      Anything else not matched cleanly      -> REFER (safe default)
    """
    reasoning: list[str] = []
    policy_refs: list[str] = []

    grade = (risk_grade or "").upper()
    dti_tier = (dti_risk_tier or "unknown").lower()

    # ---- Hard decline conditions -------------------------------------------
    if grade in ("D", "E"):
        reasoning.append(
            f"Risk grade {grade} (PD {pd_probability_ens:.1%}) exceeds acceptable "
            "default probability threshold for approval."
        )
        policy_refs.append("Basel III PD Risk Grade D/E — decline recommended")
        decision = "DECLINE"

    elif dti_tier == "high":
        reasoning.append(
            f"DTI ratio {dti_ratio:.2f} classified as high risk "
            "(>=0.50), exceeding RBI prudential threshold."
        )
        policy_refs.append("RBI DTI threshold — Section 4, high risk >= 50%")
        decision = "DECLINE"

    elif credit_score is not None and credit_score < 550:
        reasoning.append(
            f"Credit score {credit_score:.0f} falls below the minimum "
            "threshold of 550 for any product line."
        )
        policy_refs.append("RBI Section 5 — minimum credit score requirement")
        decision = "DECLINE"

    # ---- Approve conditions -------------------------------------------------
    elif grade in ("A", "B") and dti_tier in ("low", "moderate"):
        reasoning.append(
            f"Risk grade {grade} (PD {pd_probability_ens:.1%}) falls within "
            "standard approval threshold."
        )
        if dti_ratio is not None:
            reasoning.append(
                f"DTI ratio {dti_ratio:.2f} classified as {dti_tier} risk, "
                "within approval bounds."
            )
        if credit_score is not None:
            reasoning.append(
                f"Credit score {credit_score:.0f} meets minimum product requirements."
            )
        policy_refs.append("Basel III PD Risk Grade A/B — standard approval")
        policy_refs.append("RBI DTI threshold — low/moderate risk band")
        decision = "APPROVE"

    # ---- Everything else -> manual review ------------------------------------
    else:
        reasoning.append(
            f"Risk grade {grade} (PD {pd_probability_ens:.1%}) combined with "
            f"DTI tier '{dti_tier}' requires senior credit officer review."
        )
        policy_refs.append("Basel III PD Risk Grade C — enhanced monitoring")
        decision = "REFER"

    confidence = (
        "high" if decision in ("APPROVE", "DECLINE") and len(reasoning) >= 2
        else "medium"
    )

    return {
        "decision":    decision,
        "confidence":  confidence,
        "reasoning":   reasoning,
        "policy_refs": policy_refs,
    }
