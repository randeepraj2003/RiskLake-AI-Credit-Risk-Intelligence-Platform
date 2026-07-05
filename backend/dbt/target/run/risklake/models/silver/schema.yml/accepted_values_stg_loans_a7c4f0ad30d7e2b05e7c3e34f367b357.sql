
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    

with all_values as (

    select
        employment_type as value_field,
        count(*) as n_records

    from "risklake"."silver_silver"."stg_loans"
    group by employment_type

)

select *
from all_values
where value_field not in (
    'salaried','self_employed','contract','unemployed'
)



  
  
      
    ) dbt_internal_test