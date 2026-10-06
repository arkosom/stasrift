# Stasrift 1.0.0

Structure can stay compatible while meaning breaks.

Stasrift 1.0 is the first stable release of the local semantic compatibility checker.

## Highlights

- semantic compatibility verdicts: UNCHANGED / NARROWED / WIDENED / INCOMPATIBLE
- local scan / suggest / review workflow
- human confirmation before semantic writes
- SQL, CTE, and conservative dbt/Jinja lineage support
- explicit uncertainty for ambiguous joins and UNIONs
- time-axis, unit, and absent-value semantics
- two public-project pilot lessons incorporated before 1.0

## Core proof

A shape-only check sees:

`occurred_at: timestamp` -> `occurred_at: timestamp`

and passes.

Stasrift also sees:

`event_time` -> `processing_time`

and returns:

`INCOMPATIBLE`

## Install

Use the wheel attached to this release until the PyPI package is published.

## Philosophy

Stasrift was derived from the J = 0 / Jameson Zero Condition work. It does not claim new science. Its practical question is:

**Unchanged according to what?**
