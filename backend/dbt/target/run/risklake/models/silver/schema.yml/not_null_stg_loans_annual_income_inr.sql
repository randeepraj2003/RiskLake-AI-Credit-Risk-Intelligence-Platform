
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select annual_income_inr
from "risklake"."silver_silver"."stg_loans"
where annual_income_inr is null



  
  
      
    ) dbt_internal_test