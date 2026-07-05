/*
  RiskLake — Silver Layer
  Model  : feat_dti_ratio
  Schema : silver
  Depends: stg_loans, stg_credit

  Purpose
  -------
  Computes the Debt-to-Income (DTI) ratio feature for each loan application.
  DTI is one of the strongest predictors of default and is a required input
  for the Gold layer PD (Probability of Default) model.

  DTI = (estimated_monthly_debt_obligations) / (monthly_income)

  Monthly debt estimation
  -----------------------
  We don't have the customer's actual monthly outgoings from a single source,
  so we approximate from bureau + application data:

      monthly_emi_estimate  = loan_amount / loan_term_months
      bureau_monthly_burden = total_balance / 60   (assume 5-yr repayment)
      total_monthly_debt    = monthly_emi_estimate + bureau_monthly_burden

  This approximation is documented and intentional — Silver models are explicit
  about assumptions so Gold analysts can override them.

  Risk tiers (aligned with RBI prudential norms)
  -----------------------------------------------
  DTI < 0.36  →  low
  DTI < 0.43  →  moderate      (43 % is the QM threshold in many frameworks)
  DTI < 0.50  →  elevated
  DTI >= 0.50 →  high          (RBI caution zone)

  Grain: one row per loan application.
*/

{{ config(
    materialized = 'table',
    schema       = 'silver',
    indexes      = [
        {'columns': ['application_id'], 'unique': True},
        {'columns': ['customer_id']},
    ],
    tags         = ['silver', 'feature', 'dti']
) }}

with

loans as (

    select
        application_id,
        customer_id,
        application_date,
        loan_amount_inr,
        loan_term_months,
        annual_income_inr,
        employment_type,
        loan_purpose,
        credit_score,
        loan_to_income_ratio,
        collateral_coverage_ratio,
        credit_risk_tier,
        default_flag
    from {{ ref('stg_loans') }}

),

bureau as (

    select
        customer_id,
        total_balance_inr,
        total_credit_limit_inr,
        credit_utilisation_pct,
        delinquent_accounts,
        hard_inquiries_6m,
        delinquency_rate,
        high_inquiry_flag,
        utilisation_band
    from {{ ref('stg_credit') }}

),

joined as (

    select
        l.application_id,
        l.customer_id,
        l.application_date,
        l.annual_income_inr,
        l.loan_amount_inr,
        l.loan_term_months,
        l.employment_type,
        l.loan_purpose,
        l.credit_score,
        l.loan_to_income_ratio,
        l.collateral_coverage_ratio,
        l.credit_risk_tier,
        l.default_flag,

        -- Bureau signals (null-safe — not every applicant has a bureau record)
        coalesce(b.total_balance_inr,       0)          as bureau_total_balance_inr,
        coalesce(b.total_credit_limit_inr,  0)          as bureau_credit_limit_inr,
        coalesce(b.credit_utilisation_pct,  0)          as bureau_utilisation_pct,
        coalesce(b.delinquent_accounts,     0)          as delinquent_accounts,
        coalesce(b.hard_inquiries_6m,       0)          as hard_inquiries_6m,
        coalesce(b.delinquency_rate,        0)          as delinquency_rate,
        coalesce(b.high_inquiry_flag,       0)          as high_inquiry_flag,
        coalesce(b.utilisation_band, 'unknown')         as utilisation_band,

        -- Flag customers with no bureau record at all
        case when b.customer_id is null then 1 else 0
        end                                             as no_bureau_record_flag

    from loans l
    left join bureau b using (customer_id)

),

dti_computed as (

    select
        *,

        -- ── Monthly income ───────────────────────────────────────────────
        round(cast(annual_income_inr as numeric) / 12, 2)
                                                        as monthly_income_inr,

        -- ── New loan EMI estimate (simple flat division) ─────────────────
        case
            when loan_term_months > 0
            then round(cast(loan_amount_inr as numeric) / loan_term_months, 2)
            else null
        end                                             as estimated_monthly_emi_inr,

        -- ── Existing bureau debt monthly burden ──────────────────────────
        -- Assume outstanding balance repaid over 60 months (5 years)
        round(cast(bureau_total_balance_inr as numeric) / 60, 2)
                                                        as bureau_monthly_burden_inr

    from joined

),

dti_final as (

    select
        *,

        -- ── Total monthly debt obligation ────────────────────────────────
        coalesce(estimated_monthly_emi_inr, 0)
        + coalesce(bureau_monthly_burden_inr, 0)        as total_monthly_debt_inr,

        -- ── DTI ratio ────────────────────────────────────────────────────
        case
            when monthly_income_inr > 0
            then round(
                (
                    coalesce(estimated_monthly_emi_inr,  0)
                    + coalesce(bureau_monthly_burden_inr, 0)
                ) / monthly_income_inr,
                4
            )
            else null
        end                                             as dti_ratio

    from dti_computed

),

tiered as (

    select
        *,

        -- ── DTI risk tier ────────────────────────────────────────────────
        case
            when dti_ratio is null      then 'unknown'
            when dti_ratio < 0.36       then 'low'
            when dti_ratio < 0.43       then 'moderate'
            when dti_ratio < 0.50       then 'elevated'
            else                             'high'
        end                                             as dti_risk_tier,

        -- ── Combined risk flag: high DTI + high inquiry = red flag ───────
        case
            when dti_ratio >= 0.50 and high_inquiry_flag = 1 then 1
            else 0
        end                                             as combined_risk_flag,

        -- ── Audit ───────────────────────────────────────────────────────
        current_timestamp                               as feature_computed_at

    from dti_final

)

select * from tiered
