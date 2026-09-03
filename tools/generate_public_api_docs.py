#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "mcw_core" / "api"


def module_path(module: str) -> Path:
    return ROOT / (module.replace(".", "/") + ".py")


def unparse(node):
    try:
        return ast.unparse(node)
    except Exception:
        return "..."


def signature(node: ast.FunctionDef | ast.AsyncFunctionDef, *, method=False) -> str:
    a = node.args
    parts = []
    positional = list(a.posonlyargs) + list(a.args)
    defaults = [None] * (len(positional) - len(a.defaults)) + list(a.defaults)
    posonly_count = len(a.posonlyargs)
    emitted = 0
    for arg, default in zip(positional, defaults):
        if method and arg.arg in {"self", "cls"}:
            continue
        text = arg.arg
        if arg.annotation is not None:
            text += ": " + unparse(arg.annotation)
        if default is not None:
            text += " = " + unparse(default)
        parts.append(text)
        emitted += 1
        if posonly_count and emitted == posonly_count:
            parts.append("/")
    if a.vararg:
        text = "*" + a.vararg.arg
        if a.vararg.annotation is not None:
            text += ": " + unparse(a.vararg.annotation)
        parts.append(text)
    elif a.kwonlyargs:
        parts.append("*")
    for arg, default in zip(a.kwonlyargs, a.kw_defaults):
        text = arg.arg
        if arg.annotation is not None:
            text += ": " + unparse(arg.annotation)
        if default is not None:
            text += " = " + unparse(default)
        parts.append(text)
    if a.kwarg:
        text = "**" + a.kwarg.arg
        if a.kwarg.annotation is not None:
            text += ": " + unparse(a.kwarg.annotation)
        parts.append(text)
    prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
    result = f"{prefix}{node.name}({', '.join(parts)})"
    if node.returns is not None:
        result += " -> " + unparse(node.returns)
    return result


def literal_all(tree: ast.Module):
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
                value = node.value
                try:
                    result = ast.literal_eval(value)
                    if isinstance(result, (list, tuple, set)):
                        return {str(x) for x in result}
                except Exception:
                    return None
    return None


def direct_public_defs(tree: ast.Module, only_names=None):
    result = []
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):
                continue
            if only_names is not None and node.name not in only_names:
                continue
            result.append(node)
    return result


def resolve_public_module(public_file: Path):
    tree = ast.parse(public_file.read_text(encoding="utf-8"))
    resolved = []
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or not node.module or not node.module.startswith("src."):
            continue
        source_file = module_path(node.module)
        if not source_file.exists():
            continue
        source_tree = ast.parse(source_file.read_text(encoding="utf-8"))
        star = any(alias.name == "*" for alias in node.names)
        if star:
            names = literal_all(source_tree)
            defs = direct_public_defs(source_tree, names)
        else:
            names = {alias.name for alias in node.names}
            defs = direct_public_defs(source_tree, names)
        resolved.append((node.module, source_file, defs))
    return resolved


def class_lines(node: ast.ClassDef):
    lines = [f"#### `{node.name}`", ""]
    doc = ast.get_docstring(node)
    if doc:
        lines.extend([doc.split("\n\n", 1)[0].replace("\n", " "), ""])
    bases = [unparse(base) for base in node.bases]
    if bases:
        lines.extend(["Bases: `" + "`, `".join(bases) + "`", ""])

    fields = []
    constants = []
    methods = []
    for item in node.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name) and not item.target.id.startswith("_"):
            text = f"{item.target.id}: {unparse(item.annotation)}"
            if item.value is not None:
                text += " = " + unparse(item.value)
            fields.append(text)
        elif isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name) and not target.id.startswith("_") and target.id.isupper():
                    constants.append(f"{target.id} = {unparse(item.value)}")
        elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and not item.name.startswith("_"):
            decorators = {unparse(d) for d in item.decorator_list}
            methods.append((item, decorators))

    if fields:
        lines += ["Fields / public attributes:", ""]
        lines += [f"- `{x}`" for x in fields] + [""]
    if constants:
        lines += ["Public constants:", ""]
        lines += [f"- `{x}`" for x in constants] + [""]
    if methods:
        lines += ["Methods:", ""]
        for method, decorators in methods:
            tag = ""
            if "classmethod" in decorators:
                tag = "*(classmethod)*"
            elif "staticmethod" in decorators:
                tag = "*(staticmethod)*"
            elif "property" in decorators:
                tag = "*(property)*"
                lines += ["```python", signature(method, method=True), "```"]
                if tag:
                    lines += [tag]
                lines += [""]
    return lines


def function_lines(node):
    return [f"#### `{node.name}`", "", f"```python\n{signature(node)}\n```", ""]


def top_level_reference():
    sections = []
    for rel in ["mcw_core/facade.py", "mcw_core/models.py", "mcw_core/operations.py", "mcw_core/paths.py", "mcw_core/services.py"]:
        path = ROOT / rel
        tree = ast.parse(path.read_text(encoding="utf-8"))
        defs = direct_public_defs(tree)
        sections += [f"### `{rel}`", ""]
        for node in defs:
            if isinstance(node, ast.ClassDef):
                sections += class_lines(node)
            else:
                sections += function_lines(node)
    return sections


def render(language: str):
    vi = language == "vi"
    lines = [
        "# MCW Core v1.5.0 API Reference",
        "",
        ("Tài liệu này được sinh trực tiếp từ source public của MCW Core v1.5.0. "
         "Public boundary được hỗ trợ là `mcw_core` và `mcw_core.api.*`."
         if vi else
         "This reference is generated directly from the MCW Core v1.5.0 public source. "
         "The supported public boundary is `mcw_core` and `mcw_core.api.*`."),
        "",
        ("> Không import `src.core.*` hoặc `src.models.*` từ application bên ngoài."
         if vi else
         "> External consumers should not import `src.core.*` or `src.models.*` directly."),
        "",
        "## Stable facade and models",
        "",
    ]
    lines += top_level_reference()
    lines += ["## Granular `mcw_core.api.*` modules", ""]

    coverage = {"version": "1.5.0", "modules": []}
    files = sorted(p for p in API_ROOT.rglob("*.py") if p.name != "__init__.py")
    for public_file in files:
        public_module = ".".join(public_file.relative_to(ROOT).with_suffix("").parts)
        resolved = resolve_public_module(public_file)
        lines += [f"### `{public_module}`", ""]
        symbols = []
        for source_module, source_file, defs in resolved:
            lines += [f"Source re-export: `{source_module}`", ""]
            for node in defs:
                symbols.append(node.name)
                if isinstance(node, ast.ClassDef):
                    lines += class_lines(node)
                else:
                    lines += function_lines(node)
        coverage["modules"].append({
            "module": public_module,
            "source_modules": [x[0] for x in resolved],
            "symbols": symbols,
        })
    return "\n".join(lines).rstrip() + "\n", coverage


def main():
    en, coverage = render("en")
    vi, _ = render("vi")
    (ROOT / "docs/en/API_REFERENCE.md").write_text(en, encoding="utf-8")
    (ROOT / "docs/vi/API_REFERENCE.md").write_text(vi, encoding="utf-8")
    coverage["module_count"] = len(coverage["modules"])
    coverage["symbol_count"] = sum(len(x["symbols"]) for x in coverage["modules"])
    (ROOT / "docs/API_COVERAGE.json").write_text(json.dumps(coverage, indent=2) + "\n", encoding="utf-8")
    print(f"Generated API reference for {coverage['module_count']} modules / {coverage['symbol_count']} symbols")


if __name__ == "__main__":
    main()
