from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
MAIN_WINDOW = PROJECT_ROOT / "src" / "gui" / "main_window.py"
PROGRESS_SYMBOLS = {"ProgressEvent", "ProgressState", "ProgressStage"}


def test_main_window_imports_every_progress_symbol_it_uses() -> None:
    tree = ast.parse(MAIN_WINDOW.read_text(encoding="utf-8"), filename=str(MAIN_WINDOW))
    used = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in PROGRESS_SYMBOLS
    }
    imported: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        module = str(node.module or "")
        if not module.startswith("src.models.progress."):
            continue
        imported.update(alias.asname or alias.name for alias in node.names)

    assert used <= imported, f"Missing progress imports in main_window.py: {sorted(used - imported)}"
