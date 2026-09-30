from __future__ import annotations

import ast
import json
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]
_SOURCE_ROOT = _REPO_ROOT / "src"
_GUI_ROOT = _SOURCE_ROOT / "gui"
_LANGUAGE_PATH = _REPO_ROOT / "lang" / "en-US.json"

_WIDGET_CALL_ARGUMENTS = {
    "QLabel": (0,),
    "QPushButton": (0,),
    "QCheckBox": (0,),
    "QRadioButton": (0,),
    "QTableWidgetItem": (0,),
    "ThemedAnimatedLabel": (0,),
    "QGroupBox": (0,),
    "CardWidget": (0, 1),
    "SettingsSection": (0, 1),
    "BasePage": (0, 1),
    "QAction": (0,),
}
_METHOD_CALL_ARGUMENTS = {
    "setText": (0,),
    "setToolTip": (0,),
    "setStatusTip": (0,),
    "setWindowTitle": (0,),
    "setPlaceholderText": (0,),
    "addTab": (1,),
    "setTabText": (1,),
    "addItem": (0,),
}
_ALLOWED_UNTRANSLATED: set[str] = set()


def _literal_argument(call: ast.Call, index: int) -> str | None:
    if index >= len(call.args):
        return None
    argument = call.args[index]
    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
        return argument.value
    return None


def test_static_gui_text_has_translation_key_or_english_alias() -> None:
    language_data = json.loads(_LANGUAGE_PATH.read_text(encoding="utf-8"))
    translations = set(language_data["translations"])
    aliases = language_data["aliases"]
    unresolved: list[str] = []

    for path in sorted(_GUI_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            function = node.func
            argument_indices: tuple[int, ...] = ()
            label = ""
            if isinstance(function, ast.Name) and function.id in _WIDGET_CALL_ARGUMENTS:
                label = function.id
                argument_indices = _WIDGET_CALL_ARGUMENTS[function.id]
            elif isinstance(function, ast.Attribute) and function.attr in _METHOD_CALL_ARGUMENTS:
                label = function.attr
                argument_indices = _METHOD_CALL_ARGUMENTS[function.attr]
            elif isinstance(function, ast.Attribute) and function.attr in {"information", "warning", "critical", "question"}:
                label = f"QMessageBox.{function.attr}"
                argument_indices = (1, 2)

            for index in argument_indices:
                text = _literal_argument(node, index)
                if not text or not text.strip() or text in _ALLOWED_UNTRANSLATED:
                    continue
                if text not in translations and text not in aliases:
                    relative = path.relative_to(_REPO_ROOT)
                    unresolved.append(f"{relative}:{node.lineno} [{label}] {text!r}")

            if isinstance(function, ast.Name) and function.id == "tr":
                text = _literal_argument(node, 0)
                if text and text not in translations and text not in aliases:
                    relative = path.relative_to(_REPO_ROOT)
                    unresolved.append(f"{relative}:{node.lineno} [tr] {text!r}")

    assert unresolved == [], "Untranslated static GUI text:\n" + "\n".join(unresolved)


def test_all_english_aliases_point_to_existing_translation_keys() -> None:
    language_data = json.loads(_LANGUAGE_PATH.read_text(encoding="utf-8"))
    translations = set(language_data["translations"])
    invalid = {source: key for source, key in language_data["aliases"].items() if key not in translations}

    assert invalid == {}


def test_all_literal_translation_calls_resolve_in_english_pack() -> None:
    language_data = json.loads(_LANGUAGE_PATH.read_text(encoding="utf-8"))
    translations = set(language_data["translations"])
    aliases = language_data["aliases"]
    unresolved: list[str] = []

    for path in sorted(_SOURCE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            is_translation_call = (
                isinstance(function, ast.Name) and function.id == "tr"
            ) or (
                isinstance(function, ast.Attribute) and function.attr == "translate"
            )
            if not is_translation_call:
                continue
            text = _literal_argument(node, 0)
            if text and text not in translations and text not in aliases:
                relative = path.relative_to(_REPO_ROOT)
                unresolved.append(f"{relative}:{node.lineno} {text!r}")

    assert unresolved == [], "Unresolved literal translation calls:\n" + "\n".join(unresolved)


def test_builtin_language_packs_have_matching_non_empty_translations_and_valid_aliases() -> None:
    packs = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((_REPO_ROOT / "lang").glob("*.json"))
    }
    english_keys = set(packs["en-US"]["translations"])

    for locale, data in packs.items():
        translations = data["translations"]
        assert set(translations) == english_keys, f"{locale} translation keys do not match en-US"
        assert all(isinstance(value, str) and value.strip() for value in translations.values()), f"{locale} contains empty translations"
        invalid_aliases = {source: key for source, key in data.get("aliases", {}).items() if key not in translations}
        assert invalid_aliases == {}, f"{locale} aliases point to missing keys: {invalid_aliases}"


def _runtime_text_template(argument: ast.AST) -> str | None:
    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
        return argument.value
    if not isinstance(argument, ast.JoinedStr):
        return None

    parts: list[str] = []
    for value in argument.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            parts.append(value.value)
        elif isinstance(value, ast.FormattedValue):
            parts.append("{}")
        else:
            return None
    return "".join(parts)


def _normalize_runtime_template(text: str) -> str:
    import re

    return re.sub(r"\{[^{}]+\}", "{}", text)


def test_controller_task_and_status_text_has_runtime_translation() -> None:
    language_data = json.loads(_LANGUAGE_PATH.read_text(encoding="utf-8"))
    translated_templates = {
        _normalize_runtime_template(value)
        for value in language_data["translations"].values()
    }
    unresolved: list[str] = []

    for path in sorted((_GUI_ROOT / "controllers").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue

            candidate: ast.AST | None = None
            label = ""
            if node.func.attr == "run" and "task_runner" in ast.unparse(node.func.value):
                if len(node.args) >= 3:
                    candidate = node.args[2]
                else:
                    candidate = next((item.value for item in node.keywords if item.arg == "message"), None)
                label = "TaskRunner.run"
            elif node.func.attr == "emit" and isinstance(node.func.value, ast.Attribute):
                signal_name = node.func.value.attr
                if signal_name in {"status_changed", "task_rejected"} and node.args:
                    candidate = node.args[0]
                    label = f"{signal_name}.emit"

            if candidate is None:
                continue
            template = _runtime_text_template(candidate)
            if not template:
                continue
            if _normalize_runtime_template(template) not in translated_templates:
                relative = path.relative_to(_REPO_ROOT)
                unresolved.append(f"{relative}:{node.lineno} [{label}] {template!r}")

    task_runner_path = _GUI_ROOT / "task_runner.py"
    task_runner_tree = ast.parse(task_runner_path.read_text(encoding="utf-8"), filename=str(task_runner_path))
    for node in ast.walk(task_runner_tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "emit" or not isinstance(node.func.value, ast.Attribute):
            continue
        if node.func.value.attr != "task_rejected" or not node.args:
            continue
        template = _runtime_text_template(node.args[0])
        if template and _normalize_runtime_template(template) not in translated_templates:
            relative = task_runner_path.relative_to(_REPO_ROOT)
            unresolved.append(f"{relative}:{node.lineno} [task_rejected.emit] {template!r}")

    assert unresolved == [], "Untranslated controller runtime text:\n" + "\n".join(unresolved)
