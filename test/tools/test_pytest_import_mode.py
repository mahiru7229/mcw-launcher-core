from __future__ import annotations

from pathlib import Path
import tomllib


def test_pytest_uses_importlib_mode_to_isolate_duplicate_test_basenames() -> None:
    project_root = Path(__file__).resolve().parents[2]
    data = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))
    addopts = str(data["tool"]["pytest"]["ini_options"].get("addopts", ""))
    assert "--import-mode=importlib" in addopts.split()
