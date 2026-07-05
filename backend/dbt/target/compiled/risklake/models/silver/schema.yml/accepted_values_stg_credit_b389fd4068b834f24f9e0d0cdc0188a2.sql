
    
    

with all_values as (

    select
        utilisation_band as value_field,
        count(*) as n_records

    from "risklake"."silver_silver"."stg_credit"
    group by utilisation_band

)

select *
from all_values
where value_field not in (
    'low','medium','high','maxed_out'
)


