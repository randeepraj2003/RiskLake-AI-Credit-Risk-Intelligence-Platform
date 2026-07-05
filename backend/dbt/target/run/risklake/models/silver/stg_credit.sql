
  
    

  create  table "risklake"."silver_silver"."stg_credit__dbt_tmp"
  
  
    as
  
  (
    /*
  RiskLake — Silver Layer
  Model  : stg_credit
  Schema : silver
  Source : bronze.credit_bureau

  Purpose
  -------
  Cleans and enriches credit bureau pull data. Adds computed signals that
  the Gold PD model and feat_credit_util feature model consume.

  Transformations
  ---------------
  1. Type casting — everything arrives as TEXT from Bronze.
  2. Utilisation band bucketing for model inputs.
  3. Inquiry velocity flag (>=3 hard inquiries in 6 months = elevated risk).
  4. Available credit headroom calculation.
  5. Deduplication — keep the most recent bureau pull per customer.

  Grain: one row per customer (most recent bureau pull).
*/



with

source as (

    select * from "risklake"."bronze"."credit_bureau"

),

cleaned as (

    select
        -- ── Keys ────────────────────────────────────────────────────────
        trim(customer_id)                                   as customer_id,
        cast(bureau_pull_date as date)                      as bureau_pull_date,

        -- ── Core bureau fields ───────────────────────────────────────────
        cast(credit_score            as integer)            as credit_score,
        cast(total_accounts          as integer)            as total_accounts,
        cast(open_accounts           as integer)            as open_accounts,
        cast(delinquent_accounts     as integer)            as delinquent_accounts,
        cast(hard_inquiries_6m       as integer)            as hard_inquiries_6m,
        cast(oldest_account_months   as integer)            as oldest_account_months,
        cast(total_credit_limit_inr  as bigint)             as total_credit_limit_inr,
        cast(total_balance_inr       as bigint)             as total_balance_inr,

        -- Utilisation — clamp to [0,1] in case of dirty upstream values
        greatest(0, least(1,
            cast(credit_utilisation_pct as numeric)
        ))                                                  as credit_utilisation_pct,

        -- ── Derived: available credit headroom ───────────────────────────
        greatest(0,
            cast(total_credit_limit_inr as bigint)
            - cast(total_balance_inr    as bigint)
        )                                                   as available_credit_inr,

        -- ── Utilisation band (used as categorical feature in Gold ML) ────
        case
            when cast(credit_utilisation_pct as numeric) < 0.30 then 'low'
            when cast(credit_utilisation_pct as numeric) < 0.60 then 'medium'
            when cast(credit_utilisation_pct as numeric) < 0.90 then 'high'
            else 'maxed_out'
        end                                                 as utilisation_band,

        -- ── Inquiry velocity flag ────────────────────────────────────────
        -- >=3 hard inquiries in 6 months signals credit-hungry behaviour
        case
            when cast(hard_inquiries_6m as integer) >= 3 then 1
            else 0
        end                                                 as high_inquiry_flag,

        -- ── Delinquency rate ─────────────────────────────────────────────
        case
            when cast(total_accounts as integer) > 0
            then round(
                cast(delinquent_accounts as numeric)
                / cast(total_accounts    as numeric),
                4
            )
            else 0
        end                                                 as delinquency_rate,

        -- ── Credit age band ──────────────────────────────────────────────
        case
            when cast(oldest_account_months as integer) < 12  then 'new'
            when cast(oldest_account_months as integer) < 36  then 'developing'
            when cast(oldest_account_months as integer) < 84  then 'established'
            else 'mature'
        end                                                 as credit_age_band,

        -- ── Audit ───────────────────────────────────────────────────────
        current_timestamp                                   as silver_processed_at

    from source
    where customer_id is not null

),

-- Most recent bureau pull per customer
deduped as (

    select distinct on (customer_id)
        *
    from cleaned
    order by customer_id, bureau_pull_date desc

)

select * from deduped
  );
  