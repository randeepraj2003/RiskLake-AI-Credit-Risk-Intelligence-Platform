
    
    

with all_values as (

    select
        credit_age_band as value_field,
        count(*) as n_records

    from "risklake"."silver_silver"."stg_credit"
    group by credit_age_band

)

select *
from all_values
where value_field not in (
    'new','developing','established','mature'
)


