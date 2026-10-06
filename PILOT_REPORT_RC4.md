# Stasrift RC4 public pilot report

## Pilot 1 lesson retained

RC3 learned that `amount / 100` does not prove USD.

That remains human-only unless explicit currency evidence exists.

## Pilot 2

The current dbt Labs Jaffle Shop public project documents:

- `order_total` as an amount in USD
- `ordered_at` as the timestamp the order was placed
- `ordered_at` as a time dimension in the Semantic Layer

RC4 adds conservative documentation evidence so these explicit declarations can
support review suggestions.

Expected:

- `ordered_at` -> event_time
- `order_total` -> USD

Neither is written automatically.
