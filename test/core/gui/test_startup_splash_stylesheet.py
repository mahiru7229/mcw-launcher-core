from __future__ import annotations

import ast
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]
_SPLASH_PATH = _REPO_ROOT / "src" / "gui" / "startup_splash.py"


def test_startup_splash_stylesheet_only_interpolates_palette_values() -> None:
    tree = ast.parse(_SPLASH_PATH.read_text(encoding="utf-8"), filename=str(_SPLASH_PATH))
    interpolations: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "setStyleSheet" or not node.args or not isinstance(node.args[0], ast.JoinedStr):
            continue

        interpolations.extend(
            ast.unparse(value.value)
            for value in node.args[0].values
            if isinstance(value, ast.FormattedValue)
        )

    assert interpolations == ["colors.primary_pressed", "colors.primary_pressed", "colors.primary"]
