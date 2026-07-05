
    
    

with all_values as (

    select
        utilisation_change_flag as value_field,
        count(*) as n_records

    from "risklake"."silver_silver"."feat_credit_util"
    group by utilisation_change_flag

)

select *
from all_values
where value_field not in (
    '0','1'
)


