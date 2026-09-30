from __future__ import annotations

import ast
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]
_PACKAGE_INITIALIZERS = (
    _REPO_ROOT / "src" / "gui" / "animation" / "__init__.py",
    _REPO_ROOT / "src" / "gui" / "theme" / "__init__.py",
    _REPO_ROOT / "src" / "gui" / "widget" / "__init__.py",
)


def test_gui_package_exports_are_lazy_to_prevent_circular_imports() -> None:
    for path in _PACKAGE_INITIALIZERS:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        eager_gui_imports: list[str] = []
        function_names = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}

        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and str(node.module or "").startswith("src.gui"):
                eager_gui_imports.append(str(node.module))
            elif isinstance(node, ast.Import):
                eager_gui_imports.extend(alias.name for alias in node.names if alias.name.startswith("src.gui"))

        assert eager_gui_imports == [], f"Eager GUI imports in {path.relative_to(_REPO_ROOT)}: {eager_gui_imports}"
        assert "__getattr__" in function_names, f"Missing lazy export loader in {path.relative_to(_REPO_ROOT)}"
