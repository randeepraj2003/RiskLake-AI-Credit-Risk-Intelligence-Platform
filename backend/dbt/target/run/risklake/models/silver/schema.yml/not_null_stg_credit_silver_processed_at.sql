
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select silver_processed_at
from "risklake"."silver_silver"."stg_credit"
where silver_processed_at is null



  
  
      
    ) dbt_internal_test