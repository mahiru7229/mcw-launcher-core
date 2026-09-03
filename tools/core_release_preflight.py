from __future__ import annotations

import ast
import json
from pathlib import Path
import tomllib
import zipfile

import mcw_core
from src.config import CURSEFORGE_DEFAULT_GATEWAY_URL, UPDATE_CHANNEL, VERSION_ID


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_ROOTS = ("accounts", "backups", "cache", "instances", "logs", "runtimes")


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


def validate() -> list[str]:
    errors: list[str] = []
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    if project.get("name") != "mcw-core":
        errors.append("Distribution name must be mcw-core.")
    if project.get("version") != VERSION_ID or mcw_core.__version__ != VERSION_ID:
        errors.append("pyproject, src.config and mcw_core runtime versions must match.")
    if VERSION_ID != "1.5.0" or UPDATE_CHANNEL != "stable":
        errors.append("This source package must be Stable v1.5.0.")
    if CURSEFORGE_DEFAULT_GATEWAY_URL:
        errors.append("A default CurseForge gateway URL must not be bundled.")
    if (PROJECT_ROOT / "src" / "gui").exists():
        errors.append("The standalone Core package must not contain src/gui.")

    for root in (PROJECT_ROOT / "mcw_core", PROJECT_ROOT / "src" / "core", PROJECT_ROOT / "src" / "models"):
        for path in root.rglob("*.py"):
            for module in imported_modules(path):
                if module == "src.gui" or module.startswith("src.gui.") or module == "PySide6" or module.startswith("PySide6."):
                    errors.append(f"GUI dependency: {path.relative_to(PROJECT_ROOT)} -> {module}")

    for name in FORBIDDEN_ROOTS:
        root = PROJECT_ROOT / name
        if root.exists() and any(path.is_file() or path.is_symlink() for path in root.rglob("*")):
            errors.append(f"Private/runtime directory must not be packaged: {name}/")

    gateway = PROJECT_ROOT / "mcw-curseforge-gateway-main.zip"
    try:
        with zipfile.ZipFile(gateway) as archive:
            names = [name.replace("\\", "/") for name in archive.namelist()]
            if not any(name.endswith("/vercel.json") for name in names):
                errors.append("Gateway archive is missing vercel.json.")
            if any(name.endswith("/.env.local") or "node_modules/" in name for name in names):
                errors.append("Gateway archive contains local credentials or node_modules.")
    except (FileNotFoundError, zipfile.BadZipFile):
        errors.append("CurseForge gateway source archive is missing or invalid.")

    for locale in ("en-US", "vi-VN"):
        path = PROJECT_ROOT / "lang" / f"{locale}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload.get("translations"), dict):
                errors.append(f"Invalid language pack: {locale}")
        except (OSError, json.JSONDecodeError):
            errors.append(f"Missing or invalid language pack: {locale}")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"MCW Core release preflight passed for {VERSION_ID} ({UPDATE_CHANNEL}).")
    print("Public boundary: mcw_core and mcw_core.api.*")
    print("CurseForge gateway source: present, opt-in, no bundled credentials")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
