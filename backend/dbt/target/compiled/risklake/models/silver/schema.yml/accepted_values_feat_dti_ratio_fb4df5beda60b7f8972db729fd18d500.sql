
    
    

with all_values as (

    select
        dti_risk_tier as value_field,
        count(*) as n_records

    from "risklake"."silver_silver"."feat_dti_ratio"
    group by dti_risk_tier

)

select *
from all_values
where value_field not in (
    'low','moderate','elevated','high','unknown'
)


