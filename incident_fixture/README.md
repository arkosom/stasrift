# Historical-incident style fixture

Both schema versions keep:

- `occurred_at` as `timestamp`
- `amount` as `double`

A normal shape-only compatibility check therefore sees no type break.

But the producer changes `occurred_at` from source event time to current processing time.

Expected Stasrift result:

`INCOMPATIBLE`

because `event_time -> processing_time` changes declared temporal meaning.
