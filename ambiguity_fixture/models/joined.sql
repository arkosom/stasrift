select
  a.occurred_at as occurred_at,
  a.amount as amount
from {{ ref('events_a') }} a
join {{ ref('events_b') }} b
  on a.id = b.id
