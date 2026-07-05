
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select loan_amount_inr
from "risklake"."silver_silver"."stg_loans"
where loan_amount_inr is null



  
  
      
    ) dbt_internal_test