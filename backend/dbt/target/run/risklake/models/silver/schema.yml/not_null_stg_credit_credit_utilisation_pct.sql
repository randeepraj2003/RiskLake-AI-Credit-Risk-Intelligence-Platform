
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select credit_utilisation_pct
from "risklake"."silver_silver"."stg_credit"
where credit_utilisation_pct is null



  
  
      
    ) dbt_internal_test