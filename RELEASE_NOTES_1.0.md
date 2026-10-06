# Stasrift 1.0.0

Stasrift 1.0 is the first stable release of the local semantic compatibility checker.

## Frozen in 1.0

- `stasrift-contract-v1`
- CLI: `contract-schema`, `validate`, `doctor`, `scan`, `suggest`, `review`, `diff`, `demo`
- verdicts: `UNCHANGED`, `NARROWED`, `WIDENED`, `INCOMPATIBLE`
- semantic attributes: `time_axis`, `unit`, `absent`
- local-first trust model
- human review before semantic writes
- exact diff preview before write
- ambiguity remains uncertainty
- null semantics remain human-declared

## Pilot lessons incorporated

1. A cents-to-major-unit conversion does not prove USD.
2. Explicit documentation can support low-confidence semantic suggestions.
3. A generic time dimension does not prove a specific time axis.
4. Multi-source joins and UNIONs must not be collapsed into confident lineage.

## Product thesis

Structure can stay compatible while meaning breaks.

Stasrift makes that break visible before it silently reaches downstream systems.
