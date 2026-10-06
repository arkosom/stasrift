with staged as (
  select
    source_event_timestamp as occurred_at,
    current_timestamp as processed_at,
    raw_amount_cents / 100.0 as amount,
    coalesce(discount_pct, 0) as discount_pct
  from raw_orders
)
select
  staged.occurred_at as occurred_at,
  staged.processed_at as processed_at,
  staged.amount as amount,
  staged.discount_pct as discount_pct
from staged
