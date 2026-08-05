from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.theme.theme_manager import ThemeManager
from src.core.theme.theme_validation import ThemeValidator


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate one MCW Launcher theme directory.")
    parser.add_argument("theme", type=Path, help="Directory containing theme.json")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Write the versioned validation report as JSON")
    args = parser.parse_args()

    theme_root = args.theme.resolve()
    validator = ThemeValidator(ThemeManager(theme_root.parent))
    report = validator.validate_directory(theme_root)
    if args.as_json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"Theme: {report.name} ({report.theme_id})")
        print(f"Valid: {'yes' if report.is_valid else 'no'}")
        for issue in report.issues:
            location = f" [{issue.field}]" if issue.field else ""
            print(f"- {issue.severity.upper()} {issue.code}{location}: {issue.message}")
    raise SystemExit(0 if report.is_valid else 1)


if __name__ == "__main__":
    main()
