select
  source_event_timestamp as occurred_at,
  current_timestamp as processed_at,
  raw_amount_cents / 100.0 as amount
from {{ source('raw', 'orders') }}
