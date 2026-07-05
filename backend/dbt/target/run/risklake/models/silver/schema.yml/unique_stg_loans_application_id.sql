
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    

select
    application_id as unique_field,
    count(*) as n_records

from "risklake"."silver_silver"."stg_loans"
where application_id is not null
group by application_id
having count(*) > 1



  
  
      
    ) dbt_internal_test