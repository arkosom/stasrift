# Stasrift 1.0

Stasrift is a local semantic compatibility checker for data contracts. It is derived from the J = 0 / Speed of Static design work.

Its core question is simple:

> Did the structure stay compatible while the declared meaning changed?

## The proof

Both versions below can keep the same physical schema:

```text
occurred_at: timestamp
```

But the semantic contract can change:

```text
event_time -> processing_time
```

A shape-only checker passes. Stasrift returns `INCOMPATIBLE`.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Then:

```bash
stasrift --version
```

## Frozen v1 CLI

```bash
stasrift contract-schema
stasrift validate --contract contract.yaml
stasrift doctor --repo .
stasrift scan --repo . --contract contract.yaml --out .semcheck/evidence.json
stasrift suggest --evidence .semcheck/evidence.json --out .semcheck/suggestions.json
stasrift review --suggestions .semcheck/suggestions.json --contract contract.yaml
stasrift diff --old old.yaml --new new.yaml
stasrift demo --root .
```

## Canonical v1 contract

```yaml
stasrift_format: stasrift-contract-v1
fields:
  - name: occurred_at
    type: timestamp
    sem:
      time_axis: [event_time]

  - name: amount
    type: double
    sem:
      unit: [USD]

  - name: discount_pct
    nullable: true
    sem:
      absent: [unknown]
```

The machine-readable schema is in `schemas/stasrift-contract-v1.schema.json`.

## Verdicts

- `UNCHANGED`
- `NARROWED`
- `WIDENED`
- `INCOMPATIBLE`

Exit codes: `0` for unchanged/narrowed, `1` for widened/incompatible, `2` for malformed input.

## Trust model

Stasrift is local-first. `suggest` never writes semantic meaning. `review` is the only semantic writer, and it shows an exact diff before any write. Low-confidence guesses require human choice. Null meaning is human-only. Ambiguous joins and UNIONs remain uncertain rather than being guessed.

## Verify this release

```bash
./verify_release.sh
```

## Status

RC2 is for external pilot testing. Before 1.0 final: verify on a second OS, run a real external repository, and complete brand/trademark clearance.


## First public pilot

RC3 was tested against a transformation pattern from dbt Labs' public Jaffle
Shop project. That pilot caught a flaw in Stasrift itself: dividing cents by
100 does not prove the currency is USD.

RC3 now refuses that inference and asks for a human unit declaration instead.

See `PILOT_REPORT.md`.


## Public pilot 2

RC4 adds a second public-project pilot based on the current dbt Labs Jaffle Shop
model documentation.

Explicit documentation can now contribute evidence:

- `order_total` documented in USD -> review suggestion for `USD`
- `ordered_at` documented as when the order was placed -> review suggestion for `event_time`
- a generic Semantic Layer time dimension without axis detail -> human question, not an automatic choice

See `PILOT_REPORT_RC4.md`.


## 1.0 status

The v1 contract format and CLI are frozen.

Future 1.x releases may add parsers, adapters, and evidence sources without changing the meaning of existing v1 semantic declarations.
