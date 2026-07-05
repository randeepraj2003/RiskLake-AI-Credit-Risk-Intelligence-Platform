
    
    

with all_values as (

    select
        combined_risk_flag as value_field,
        count(*) as n_records

    from "risklake"."silver_silver"."feat_dti_ratio"
    group by combined_risk_flag

)

select *
from all_values
where value_field not in (
    '0','1'
)


