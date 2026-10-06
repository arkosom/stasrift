with source as (
  select * from {{ source('ecom', 'raw_orders') }}
),
renamed as (
  select
    {{ dbt.date_trunc('day','ordered_at') }} as ordered_at,
    {{ cents_to_dollars('order_total') }} as order_total
  from source
)
select * from renamed
