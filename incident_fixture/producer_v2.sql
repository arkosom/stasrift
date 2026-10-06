select
  current_timestamp as occurred_at,
  raw_amount_cents / 100.0 as amount
from raw_orders
