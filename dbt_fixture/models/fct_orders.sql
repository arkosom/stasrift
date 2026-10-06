select
  occurred_at,
  processed_at,
  amount
from {{ ref('stg_orders') }}
