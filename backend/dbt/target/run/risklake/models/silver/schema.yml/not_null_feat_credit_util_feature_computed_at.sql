
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select feature_computed_at
from "risklake"."silver_silver"."feat_credit_util"
where feature_computed_at is null



  
  
      
    ) dbt_internal_test