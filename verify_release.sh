#!/usr/bin/env bash
set -euo pipefail
python stasrift.py --version
python stasrift.py validate --contract examples/orders.stasrift.yaml
python baseline_shape_check.py incident_fixture/schema_v1.yaml incident_fixture/schema_v2.yaml
set +e
python stasrift.py diff --old incident_fixture/schema_v1.yaml --new incident_fixture/schema_v2.yaml
rc=$?
set -e
if [ "$rc" -ne 1 ]; then
  echo "Expected semantic incompatibility exit code 1, got $rc" >&2
  exit 1
fi
echo "Release verification passed. Run 'python -m pytest -q' separately for the full regression suite."
