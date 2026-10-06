# Public pilot 2

Pattern derived from the current dbt Labs Jaffle Shop public project:

- `ordered_at` is documented as the timestamp the order was placed at
- `ordered_at` is a Semantic Layer time dimension
- `order_total` is documented explicitly in USD

RC4 expected behavior:

- suggest `ordered_at.time_axis = event_time`
- suggest `order_total.unit = USD`
- keep all declarations human-reviewed
