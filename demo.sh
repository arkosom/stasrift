#!/usr/bin/env bash
set -euo pipefail

echo "1) Shape-only baseline"
python baseline_shape_check.py incident_fixture/schema_v1.yaml incident_fixture/schema_v2.yaml || true
echo
echo "2) Stasrift semantic diff"
python stasrift.py diff --old incident_fixture/schema_v1.yaml --new incident_fixture/schema_v2.yaml || true
echo
echo "3) Repo readiness"
python stasrift.py doctor --repo dbt_fixture || true
