
    
    

with all_values as (

    select
        credit_risk_tier as value_field,
        count(*) as n_records

    from "risklake"."silver_silver"."stg_loans"
    group by credit_risk_tier

)

select *
from all_values
where value_field not in (
    'low','medium','high','very_high'
)


