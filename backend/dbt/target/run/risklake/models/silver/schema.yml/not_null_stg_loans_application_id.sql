
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select application_id
from "risklake"."silver_silver"."stg_loans"
where application_id is null



  
  
      
    ) dbt_internal_test