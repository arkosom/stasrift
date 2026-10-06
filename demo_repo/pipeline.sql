select
  source_event_timestamp as occurred_at,
  current_timestamp as processed_at,
  current_timestamp as ship_at,
  raw_amount_cents / 100.0 as amount_usd,
  coalesce(discount_pct, 0) as discount_pct
from raw_orders
