# Stasrift RC3 public pilot report

## Repository pattern tested

A real transformation pattern from dbt Labs' public Jaffle Shop example was
used as the first external pilot.

The source SQL converts an `amount` stored in cents by dividing by 100.
The associated public schema documentation describes order amounts as AUD.

## RC2 failure discovered

RC2 treated a cents-to-major-unit conversion as evidence for `USD`.

That is unsound. "cents" does not uniquely identify the currency.

## RC3 correction

RC3 now records:

- major-currency conversion detected
- currency not inferable

and creates a human-only `unit` question instead of proposing USD.

## Why this matters

This is exactly the kind of failure Stasrift is supposed to prevent:
a tool should not replace one silent semantic assumption with another.

The first public pilot therefore changed the product behavior before 1.0 final.
