"""Explicitly run the controlled, one-time legacy JSON-to-SQL migration."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.persistence import SqlStore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=ROOT / "data")
    parser.add_argument("--source-root", type=Path, help="Legacy source root; defaults to --data-root")
    args = parser.parse_args()
    report = SqlStore(args.data_root).migrate_legacy_data_once(args.source_root or args.data_root)
    print(json.dumps(report, indent=2))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
