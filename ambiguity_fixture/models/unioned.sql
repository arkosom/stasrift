select
  occurred_at,
  amount
from {{ ref('events_a') }}
union all
select
  occurred_at,
  amount
from {{ ref('events_b') }}
