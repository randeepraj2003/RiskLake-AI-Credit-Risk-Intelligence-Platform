
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select application_date
from "risklake"."silver_silver"."stg_loans"
where application_date is null



  
  
      
    ) dbt_internal_test