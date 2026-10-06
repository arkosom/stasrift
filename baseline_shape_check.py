#!/usr/bin/env python3
from pathlib import Path
import sys, yaml

def fields(path):
    data = yaml.safe_load(Path(path).read_text())
    return {f["name"]: f.get("type") for f in data["fields"]}

a, b = fields(sys.argv[1]), fields(sys.argv[2])
if a == b:
    print("PASS: field names and physical types unchanged")
    raise SystemExit(0)
print("FAIL: structural schema changed")
raise SystemExit(1)
