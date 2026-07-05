
    
    

with all_values as (

    select
        balance_trend_flag as value_field,
        count(*) as n_records

    from "risklake"."silver_silver"."feat_credit_util"
    group by balance_trend_flag

)

select *
from all_values
where value_field not in (
    '0','1'
)


