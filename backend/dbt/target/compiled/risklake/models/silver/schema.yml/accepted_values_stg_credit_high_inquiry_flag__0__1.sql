
    
    

with all_values as (

    select
        high_inquiry_flag as value_field,
        count(*) as n_records

    from "risklake"."silver_silver"."stg_credit"
    group by high_inquiry_flag

)

select *
from all_values
where value_field not in (
    '0','1'
)


