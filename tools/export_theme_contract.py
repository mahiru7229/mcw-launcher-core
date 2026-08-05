from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.theme.theme_contract import write_contract_documents


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the frozen MCW theme runtime contract documents.")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "docs" / "schema")
    args = parser.parse_args()

    paths = write_contract_documents(args.output.resolve())
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
