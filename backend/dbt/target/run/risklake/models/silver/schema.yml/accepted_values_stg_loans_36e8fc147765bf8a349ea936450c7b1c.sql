
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    

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



  
  
      
    ) dbt_internal_test