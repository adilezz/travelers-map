"""Freeze the holdout: record its hash so any later edit is detected (document 3 section 1).

Run once, after the owner has written data/holdout/H1.csv and before any pipeline is tuned.
Changing the holdout afterwards requires deleting data/freeze.json on purpose.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    holdout = ROOT / "data" / "holdout" / "H1.csv"
    out = ROOT / "data" / "freeze.json"
    if out.exists():
        print("data/freeze.json exists: the holdout is already frozen. "
              "Delete it deliberately to refreeze.")
        return 1
    digest = hashlib.sha256(holdout.read_bytes()).hexdigest()
    out.write_text(json.dumps({"holdout_sha256": digest}, indent=2) + "\n")
    print("froze", holdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
