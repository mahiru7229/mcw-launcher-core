from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def test_validate_theme_cli_outputs_versioned_json_from_any_working_directory(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    theme = tmp_path / "themes" / "valid-theme"
    theme.mkdir(parents=True)
    (theme / "theme.json").write_text(json.dumps({"schema_version": 6, "id": "valid-theme", "assets": {}}), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(project_root / "tools" / "validate_theme.py"), str(theme), "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["valid"] is True
    assert payload["report_version"] == 1
    assert payload["contract_version"] == 1
    assert payload["schema_version"] == 6


def test_validate_theme_cli_returns_nonzero_for_invalid_theme(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    theme = tmp_path / "themes" / "invalid-theme"
    theme.mkdir(parents=True)
    (theme / "theme.json").write_text("{broken", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(project_root / "tools" / "validate_theme.py"), str(theme), "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["valid"] is False
    assert payload["issues"][0]["code"] == "THEME_MANIFEST_INVALID_JSON"
