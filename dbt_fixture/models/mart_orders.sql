select
  occurred_at,
  processed_at,
  amount
from {{ ref('fct_orders') }}
