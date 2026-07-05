
  
    

  create  table "risklake"."silver_silver"."stg_loans__dbt_tmp"
  
  
    as
  
  (
    /*
  RiskLake — Silver Layer
  Model  : stg_loans
  Schema : silver
  Source : bronze.loan_applications

  Purpose
  -------
  Cleans and standardises the raw loan application data arriving from the
  Bronze layer. This is the canonical staging model that all downstream
  Silver feature models and Gold risk tables join against.

  Transformations applied
  -----------------------
  1. Cast columns to correct data types (Bronze lands everything as TEXT).
  2. Null-safe defaults for optional fields.
  3. Derive loan_to_income_ratio — a foundational risk signal.
  4. Standardise categorical values to lowercase snake_case.
  5. Drop internal Bronze metadata columns (_bronze_*).
  6. Add silver_processed_at audit timestamp.

  Grain: one row per loan application (application_id is the PK).
*/



with

source as (

    select * from "risklake"."bronze"."loan_applications"

),

cleaned as (

    select
        -- ── Keys ────────────────────────────────────────────────────────
        trim(application_id)                            as application_id,
        trim(customer_id)                               as customer_id,

        -- ── Dates ───────────────────────────────────────────────────────
        cast(application_date as date)                  as application_date,

        -- ── Financials ──────────────────────────────────────────────────
        cast(loan_amount_inr     as bigint)             as loan_amount_inr,
        cast(annual_income_inr   as bigint)             as annual_income_inr,
        cast(loan_term_months    as integer)            as loan_term_months,
        cast(existing_loans      as integer)            as existing_loans,
        cast(collateral_value    as bigint)             as collateral_value_inr,
        cast(credit_score        as integer)            as credit_score,

        -- ── Categoricals — lowercased & trimmed ─────────────────────────
        lower(trim(employment_type))                    as employment_type,
        lower(trim(loan_purpose))                       as loan_purpose,

        -- ── Target label ────────────────────────────────────────────────
        cast(default_flag as integer)                   as default_flag,

        -- ── Derived feature: Loan-to-Income ratio ───────────────────────
        -- Protects against division-by-zero from dirty source data.
        case
            when cast(annual_income_inr as bigint) > 0
            then round(
                cast(loan_amount_inr as numeric)
                / cast(annual_income_inr as numeric),
                4
            )
            else null
        end                                             as loan_to_income_ratio,

        -- ── Collateral coverage ratio ────────────────────────────────────
        case
            when cast(loan_amount_inr as bigint) > 0
            then round(
                cast(collateral_value as numeric)
                / cast(loan_amount_inr as numeric),
                4
            )
            else null
        end                                             as collateral_coverage_ratio,

        -- ── Credit risk tier (rule-based, overridden by Gold ML model) ───
        case
            when cast(credit_score as integer) >= 750 then 'low'
            when cast(credit_score as integer) >= 600 then 'medium'
            when cast(credit_score as integer) >= 450 then 'high'
            else 'very_high'
        end                                             as credit_risk_tier,

        -- ── Audit ───────────────────────────────────────────────────────
        current_timestamp                               as silver_processed_at

    from source

    where
        -- Hard filter: reject rows with no primary key or income
        application_id   is not null
        and customer_id  is not null
        and cast(annual_income_inr as bigint) > 0

),

deduped as (

    -- Keep the latest record per application_id in case Bronze re-ingests
    select distinct on (application_id)
        *
    from cleaned
    order by application_id, silver_processed_at desc

)

select * from deduped
  );
  