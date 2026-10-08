#!/usr/bin/env python3
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
SRC = HERE / "src"
# Editable installs may already put src later on sys.path. It must precede
# this wrapper's directory, or stasrift.py shadows the stasrift package.
if str(SRC) in sys.path:
    sys.path.remove(str(SRC))
sys.path.insert(0, str(SRC))

from stasrift.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
