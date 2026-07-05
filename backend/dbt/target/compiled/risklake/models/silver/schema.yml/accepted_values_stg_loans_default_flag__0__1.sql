
    
    

with all_values as (

    select
        default_flag as value_field,
        count(*) as n_records

    from "risklake"."silver_silver"."stg_loans"
    group by default_flag

)

select *
from all_values
where value_field not in (
    '0','1'
)


