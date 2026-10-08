#!/usr/bin/env bash
set -euo pipefail
python -m venv .venv
. .venv/bin/activate
pip install -e .
stasrift --version
set +e
stasrift demo --root .
rc=$?
set -e
if [ "$rc" -ne 1 ]; then
  echo "Expected demo incompatibility exit code 1, got $rc" >&2
  exit 1
fi
