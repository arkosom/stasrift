# Public pilot: dbt Jaffle Shop pattern

This fixture reproduces the relevant transformation pattern from dbt-labs'
public Jaffle Shop example:

- `amount` is stored in cents
- SQL divides by 100
- the project's schema documentation describes order amounts in AUD

The pilot exists to test whether Stasrift falsely assumes a currency from a
cents-to-major-unit conversion.

RC3 expected behavior:

- do **not** infer USD
- ask for a human unit declaration instead

This pilot exposed and fixed an unsafe RC2 heuristic.
