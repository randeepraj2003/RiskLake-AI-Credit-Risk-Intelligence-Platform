/*
  RiskLake — Silver Layer
  Model  : feat_credit_util
  Schema : silver
  Depends: stg_credit, bronze.transactions

  Purpose
  -------
  Builds a rich credit utilisation feature set per customer by combining:
    1. Bureau snapshot utilisation (point-in-time from stg_credit)
    2. Transaction-derived behavioural signals (rolling spend velocity,
       EMI payment regularity, average monthly balance)

  These features feed directly into:
    - Gold PD model (as numeric inputs)
    - ARIMA credit utilisation forecasting (as the time series target)
    - AI Credit Analyst RAG context (as explainable customer signals)

  Key features produced
  ----------------------
  bureau_utilisation_pct     — bureau point-in-time utilisation
  avg_monthly_spend_inr      — mean monthly debit spend over 12 months
  spend_volatility_inr       — std deviation of monthly spend (stability signal)
  emi_payment_count          — number of EMI payments in window
  emi_regularity_score       — ratio of months with >=1 EMI to total months
  balance_trend_flag         — 1 if avg recent balance > avg earlier balance
  txn_utilisation_estimate   — transaction-derived utilisation proxy
  utilisation_change_flag    — 1 if txn utilisation > bureau utilisation by >15%

  Grain: one row per customer.
*/



with

bureau as (

    select
        customer_id,
        bureau_pull_date,
        credit_score,
        credit_utilisation_pct              as bureau_utilisation_pct,
        total_credit_limit_inr,
        total_balance_inr                   as bureau_balance_inr,
        utilisation_band,
        high_inquiry_flag,
        delinquency_rate,
        available_credit_inr,
        credit_age_band
    from "risklake"."silver_silver"."stg_credit"

),

-- Raw transactions — keep only the last 12 months for recency
txn_raw as (

    select
        customer_id,
        cast(transaction_date as date)      as transaction_date,
        cast(amount_inr as bigint)          as amount_inr,
        lower(trim(transaction_type))       as transaction_type,
        cast(balance_after_inr as bigint)   as balance_after_inr,
        cast(is_flagged as integer)         as is_flagged,

        -- Month bucket for rolling aggregations
        date_trunc('month', cast(transaction_date as date))
                                            as txn_month

    from "risklake"."bronze"."transactions"
    where
        customer_id      is not null
        and transaction_date is not null
        -- Rolling 12-month window relative to today
        and cast(transaction_date as date) >= current_date - interval '12 months'

),

-- Monthly spend per customer (debit transactions only)
monthly_spend as (

    select
        customer_id,
        txn_month,
        sum(case when transaction_type in ('debit', 'atm_withdrawal', 'pos')
                 then amount_inr else 0 end)    as monthly_debit_spend_inr,
        sum(case when transaction_type = 'emi_payment'
                 then amount_inr else 0 end)    as monthly_emi_paid_inr,
        count(case when transaction_type = 'emi_payment'
                   then 1 end)                  as emi_payment_count,
        avg(balance_after_inr)                  as avg_balance_inr,
        sum(is_flagged)                         as flagged_txn_count,
        count(*)                                as total_txn_count
    from txn_raw
    group by customer_id, txn_month

),

-- Aggregate to customer level
customer_txn_agg as (

    select
        customer_id,

        -- Spend signals
        round(avg(monthly_debit_spend_inr), 2)  as avg_monthly_spend_inr,
        round(stddev(monthly_debit_spend_inr), 2)
                                                as spend_volatility_inr,
        round(max(monthly_debit_spend_inr), 2)  as peak_monthly_spend_inr,

        -- EMI signals
        sum(emi_payment_count)                  as emi_payment_count_12m,
        sum(monthly_emi_paid_inr)               as total_emi_paid_inr_12m,

        -- EMI regularity: how many months had at least 1 EMI payment?
        round(
            cast(count(case when emi_payment_count > 0 then 1 end) as numeric)
            / nullif(count(*), 0),
            4
        )                                       as emi_regularity_score,

        -- Balance trend: compare recent 3m avg vs earlier 9m avg
        avg(case when txn_month >= date_trunc('month', current_date) - interval '3 months'
                 then avg_balance_inr end)      as avg_balance_recent_3m,
        avg(case when txn_month < date_trunc('month', current_date) - interval '3 months'
                 then avg_balance_inr end)      as avg_balance_earlier_9m,

        -- Risk signals
        sum(flagged_txn_count)                  as total_flagged_txns,
        sum(total_txn_count)                    as total_txns_12m,
        count(distinct txn_month)               as active_months_count

    from monthly_spend
    group by customer_id

),

-- Join bureau + transaction aggregates
combined as (

    select
        b.customer_id,
        b.bureau_pull_date,
        b.credit_score,
        b.bureau_utilisation_pct,
        b.total_credit_limit_inr,
        b.bureau_balance_inr,
        b.utilisation_band,
        b.high_inquiry_flag,
        b.delinquency_rate,
        b.available_credit_inr,
        b.credit_age_band,

        -- Transaction features (null-safe for customers with no recent txns)
        coalesce(t.avg_monthly_spend_inr,   0)  as avg_monthly_spend_inr,
        coalesce(t.spend_volatility_inr,    0)  as spend_volatility_inr,
        coalesce(t.peak_monthly_spend_inr,  0)  as peak_monthly_spend_inr,
        coalesce(t.emi_payment_count_12m,   0)  as emi_payment_count_12m,
        coalesce(t.total_emi_paid_inr_12m,  0)  as total_emi_paid_inr_12m,
        coalesce(t.emi_regularity_score,    0)  as emi_regularity_score,
        coalesce(t.avg_balance_recent_3m,   0)  as avg_balance_recent_3m,
        coalesce(t.avg_balance_earlier_9m,  0)  as avg_balance_earlier_9m,
        coalesce(t.total_flagged_txns,      0)  as total_flagged_txns,
        coalesce(t.total_txns_12m,          0)  as total_txns_12m,
        coalesce(t.active_months_count,     0)  as active_months_count,

        -- Flag: no transaction history at all
        case when t.customer_id is null then 1 else 0
        end                                     as no_txn_history_flag

    from bureau b
    left join customer_txn_agg t using (customer_id)

),

enriched as (

    select
        *,

        -- ── Balance trend flag ───────────────────────────────────────────
        -- 1 = recent balance growing (potential stress signal)
        case
            when avg_balance_earlier_9m > 0
             and avg_balance_recent_3m > avg_balance_earlier_9m
            then 1
            else 0
        end                                     as balance_trend_flag,

        -- ── Transaction-derived utilisation proxy ────────────────────────
        -- Monthly spend vs credit limit as a behaviour-based utilisation
        case
            when total_credit_limit_inr > 0
            then round(
                avg_monthly_spend_inr / cast(total_credit_limit_inr as numeric),
                4
            )
            else null
        end                                     as txn_utilisation_estimate,

        -- ── Flagged transaction rate ─────────────────────────────────────
        case
            when total_txns_12m > 0
            then round(
                cast(total_flagged_txns as numeric) / total_txns_12m,
                4
            )
            else 0
        end                                     as flagged_txn_rate

    from combined

),

final as (

    select
        *,

        -- ── Utilisation divergence flag ──────────────────────────────────
        -- Flags customers whose transaction behaviour implies higher
        -- utilisation than the bureau snapshot suggests (data lag risk).
        case
            when txn_utilisation_estimate is not null
             and txn_utilisation_estimate > (bureau_utilisation_pct + 0.15)
            then 1
            else 0
        end                                     as utilisation_change_flag,

        -- ── Overall credit stress score (0–4 additive flags) ────────────
        -- Used by the AI credit analyst as a quick-read summary signal.
        (
            high_inquiry_flag
            + balance_trend_flag
            + case when emi_regularity_score < 0.5 then 1 else 0 end
            + case when flagged_txn_rate > 0.05    then 1 else 0 end
        )                                       as credit_stress_score,

        -- ── Audit ───────────────────────────────────────────────────────
        current_timestamp                       as feature_computed_at

    from enriched

)

select * from final