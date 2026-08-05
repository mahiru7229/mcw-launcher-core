from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import CURSEFORGE_DEFAULT_GATEWAY_URL, UPDATE_CHANNEL, VERSION, VERSION_ID, VERSION_TAG
from src.core.lan.lan_agent_manager import LanAgentManager
from src.core.theme.theme_contract import ASSET_CATALOG_FILENAME, CONTRACT_FILENAME, SCHEMA_FILENAME, THEME_SCHEMA_VERSION, build_theme_asset_catalog_v1, build_theme_runtime_contract_v1, build_theme_schema_v6

TEXT_SUFFIXES = {".json", ".md", ".ps1", ".py", ".txt", ".yml", ".yaml"}
IGNORED_DIRECTORIES = {".git", ".pytest_cache", ".venv", "__pycache__", "build", "cache", "dist", "release"}
CONFLICT_MARKERS = ("<<<<<<<", "=======", ">>>>>>>")
PLACEHOLDER_PATTERN = re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)[^{}]*\}(?!\})")


def iter_release_text_files(project_root: Path) -> Iterable[Path]:
    for path in project_root.rglob("*"):
        if not path.is_file() or path.suffix.casefold() not in TEXT_SUFFIXES:
            continue
        if any(part in IGNORED_DIRECTORIES for part in path.relative_to(project_root).parts):
            continue
        yield path


def find_merge_markers(project_root: Path) -> list[str]:
    errors: list[str] = []
    for path in iter_release_text_files(project_root):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for line_number, line in enumerate(lines, start=1):
            if line.startswith(CONFLICT_MARKERS):
                errors.append(f"{path.relative_to(project_root)}:{line_number}: unresolved merge marker")
    return errors


def load_language_pack(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("language pack root must be an object")
    translations = payload.get("translations")
    if not isinstance(translations, dict):
        raise ValueError("language pack must contain a translations object")
    return payload


def placeholder_names(value: object) -> set[str]:
    return set(PLACEHOLDER_PATTERN.findall(str(value)))


def audit_language_packs(project_root: Path) -> list[str]:
    errors: list[str] = []
    english_path = project_root / "lang" / "en-US.json"
    vietnamese_path = project_root / "lang" / "vi-VN.json"
    try:
        english = load_language_pack(english_path)
        vietnamese = load_language_pack(vietnamese_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return [f"Language pack error: {error}"]

    english_translations = english["translations"]
    vietnamese_translations = vietnamese["translations"]
    english_keys = set(english_translations)
    vietnamese_keys = set(vietnamese_translations)

    for key in sorted(english_keys - vietnamese_keys):
        errors.append(f"vi-VN is missing translation key: {key}")
    for key in sorted(vietnamese_keys - english_keys):
        errors.append(f"en-US is missing translation key: {key}")

    for key in sorted(english_keys | vietnamese_keys):
        if key in english_translations and not str(english_translations[key]).strip():
            errors.append(f"en-US has an empty translation: {key}")
        if key in vietnamese_translations and not str(vietnamese_translations[key]).strip():
            errors.append(f"vi-VN has an empty translation: {key}")
        if key in english_translations and key in vietnamese_translations:
            english_placeholders = placeholder_names(english_translations[key])
            vietnamese_placeholders = placeholder_names(vietnamese_translations[key])
            if english_placeholders != vietnamese_placeholders:
                errors.append(
                    f"Placeholder mismatch for {key}: en-US={sorted(english_placeholders)}, "
                    f"vi-VN={sorted(vietnamese_placeholders)}"
                )
    return errors





def audit_navigation_translation_keys(project_root: Path) -> list[str]:
    """Require primary navigation labels to use semantic translation keys.

    This keeps the sidebar and startup-page selector compatible with external
    translation editors and prevents raw English labels from bypassing the
    selected language pack.
    """

    import ast

    errors: list[str] = []
    config_path = project_root / "src" / "gui" / "config.py"
    try:
        tree = ast.parse(config_path.read_text(encoding="utf-8"), filename=str(config_path))
    except (OSError, SyntaxError) as error:
        return [f"Navigation configuration error: {error}"]

    navigation = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "NAVIGATION_ITEMS" for target in node.targets):
            try:
                navigation = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError) as error:
                errors.append(f"NAVIGATION_ITEMS must be a literal tuple: {error}")
            break
    if navigation is None:
        return errors + ["src/gui/config.py is missing NAVIGATION_ITEMS"]

    packs: dict[str, dict] = {}
    for locale in ("en-US", "vi-VN"):
        try:
            packs[locale] = load_language_pack(project_root / "lang" / f"{locale}.json")["translations"]
        except (OSError, ValueError, json.JSONDecodeError) as error:
            errors.append(f"Unable to inspect {locale} navigation translations: {error}")

    seen_pages: set[str] = set()
    for item in navigation:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            errors.append(f"Invalid navigation item: {item!r}")
            continue
        page_id, text_key = str(item[0]), str(item[1])
        if page_id in seen_pages:
            errors.append(f"Duplicate navigation page id: {page_id}")
        seen_pages.add(page_id)
        if not text_key.startswith("navigation."):
            errors.append(f"Navigation item {page_id} must use a navigation.* translation key, got {text_key!r}")
        for locale, translations in packs.items():
            if text_key not in translations:
                errors.append(f"{locale} is missing navigation key {text_key} for page {page_id}")

    if packs:
        if packs.get("vi-VN", {}).get("navigation.launcher_settings") != "Cài đặt launcher":
            errors.append("vi-VN navigation.launcher_settings must be 'Cài đặt launcher'")
        for locale in ("en-US", "vi-VN"):
            if packs.get(locale, {}).get("navigation.instances") != "Instance":
                errors.append(f"{locale} navigation.instances must preserve the product term 'Instance'")
    return errors

def audit_private_gateway_bundling(project_root: Path) -> list[str]:
    """Ensure no CurseForge endpoint or credential is bundled by default.

    CurseForge support remains available, but users and deployments must provide
    their own HTTPS gateway through local protected settings or environment
    variables. Release packages must not contain a default endpoint or API key.
    """

    errors: list[str] = []
    config_path = project_root / "src" / "config.py"
    try:
        config_text = config_path.read_text(encoding="utf-8")
    except OSError as error:
        return [f"Unable to inspect src/config.py: {error}"]

    legacy_match = re.search(r'^CURSEFORGE_GATEWAY_URL\s*=\s*[\'"]([^\'"]*)', config_text, flags=re.MULTILINE)
    if legacy_match is not None:
        errors.append("Legacy CurseForge gateway constants are not allowed")

    default_match = re.search(r'^CURSEFORGE_DEFAULT_GATEWAY_URL\s*=\s*[\'"]([^\'"]*)', config_text, flags=re.MULTILINE)
    if default_match is None:
        errors.append("src/config.py must explicitly define an empty CURSEFORGE_DEFAULT_GATEWAY_URL")
    elif default_match.group(1).strip():
        errors.append("src/config.py must not bundle a default CurseForge gateway URL")

    if str(CURSEFORGE_DEFAULT_GATEWAY_URL or "").strip():
        errors.append("The imported CurseForge default gateway must be empty")

    secret_patterns = (
        r'^CURSEFORGE_API_KEY\s*=',
        r'^CURSEFORGE_X_API_KEY\s*=',
        r'[\'"]x-api-key[\'"]\s*:\s*[\'"][^\'"]+[\'"]',
    )
    if any(re.search(pattern, config_text, flags=re.MULTILINE | re.IGNORECASE) for pattern in secret_patterns):
        errors.append("CurseForge API credentials must not be bundled in src/config.py")

    example_path = project_root / "config" / "curseforge.example.json"
    try:
        example = json.loads(example_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"CurseForge config template error: {error}")
    else:
        default_url = str(example.get("default_gateway_url") or "").strip() if isinstance(example, dict) else ""
        if default_url:
            errors.append("config/curseforge.example.json must not document a bundled default gateway URL")
        bundled = example.get("bundled_gateway_urls") if isinstance(example, dict) else None
        if bundled is not None and bundled != [] and bundled != ():
            errors.append("config/curseforge.example.json must not contain bundled gateway URLs")

    gitignore_path = project_root / ".gitignore"
    try:
        gitignore = gitignore_path.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"Unable to inspect .gitignore: {error}")
    else:
        if "config/private/" not in gitignore:
            errors.append(".gitignore must exclude config/private/")
    return errors




def audit_theme_contract(project_root: Path) -> list[str]:
    errors: list[str] = []
    schema_root = project_root / "docs" / "schema"
    expected_documents = {
        SCHEMA_FILENAME: build_theme_schema_v6(),
        ASSET_CATALOG_FILENAME: build_theme_asset_catalog_v1(),
        CONTRACT_FILENAME: build_theme_runtime_contract_v1(),
    }
    for filename, expected in expected_documents.items():
        path = schema_root / filename
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            errors.append(f"Theme contract document error for {filename}: {error}")
            continue
        if payload != expected:
            errors.append(f"Theme contract document is out of date: docs/schema/{filename}")

    contract_path = schema_root / CONTRACT_FILENAME
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        contract = None
    if isinstance(contract, dict):
        hashes = contract.get("sha256")
        if not isinstance(hashes, dict):
            errors.append("Theme runtime contract is missing document hashes")
        else:
            for filename, expected_hash in hashes.items():
                path = schema_root / str(filename)
                if not path.is_file():
                    errors.append(f"Theme contract hash target is missing: docs/schema/{filename}")
                    continue
                actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
                if actual_hash != str(expected_hash):
                    errors.append(f"Theme contract SHA-256 mismatch: docs/schema/{filename}")

    default_manifest = project_root / "themes" / "mcw-default" / "theme.json"
    try:
        default_theme = json.loads(default_manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        errors.append(f"Default theme manifest error: {error}")
    else:
        if not isinstance(default_theme, dict) or default_theme.get("schema_version") != THEME_SCHEMA_VERSION:
            errors.append(f"Default theme must target frozen schema {THEME_SCHEMA_VERSION}")

    core_root = project_root / "src" / "core" / "theme"
    for path in sorted(core_root.glob("*.py")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as error:
            errors.append(f"Unable to inspect theme core module {path.name}: {error}")
            continue
        if "PySide6" in text or "src.gui" in text:
            errors.append(f"Theme core module depends on GUI code: src/core/theme/{path.name}")
    return errors

def audit_lan_agent(project_root: Path) -> list[str]:
    errors: list[str] = []
    agent_path = project_root / "runtime" / LanAgentManager.AGENT_FILENAME
    if not agent_path.is_file():
        return [f"Missing MCW LAN Agent: {agent_path.relative_to(project_root)}"]

    digest = hashlib.sha256(agent_path.read_bytes()).hexdigest()
    if digest != LanAgentManager.AGENT_SHA256:
        errors.append(f"MCW LAN Agent SHA-256 mismatch: expected {LanAgentManager.AGENT_SHA256}, got {digest}")

    try:
        with zipfile.ZipFile(agent_path) as archive:
            manifest = archive.read("META-INF/MANIFEST.MF").decode("utf-8", errors="replace")
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        errors.append(f"MCW LAN Agent JAR is invalid: {error}")
    else:
        expected = "Premain-Class: org.mcwlauncher.lanagent.McwLanAgent"
        if expected not in manifest:
            errors.append("MCW LAN Agent manifest is missing the expected Premain-Class")

    try:
        spec_text = (project_root / "mcw_launcher.spec").read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"Unable to inspect mcw_launcher.spec for LAN Agent bundling: {error}")
    else:
        if LanAgentManager.AGENT_FILENAME not in spec_text:
            errors.append("mcw_launcher.spec does not bundle the MCW LAN Agent")
    return errors

def audit_version_metadata(project_root: Path) -> list[str]:
    errors: list[str] = []
    if VERSION_TAG != f"v{VERSION_ID}":
        errors.append(f"VERSION_TAG must be v{VERSION_ID}, got {VERSION_TAG}")
    if VERSION_ID not in VERSION_TAG:
        errors.append("VERSION_ID is not represented by VERSION_TAG")
    if not VERSION.strip():
        errors.append("VERSION must not be empty")
    if UPDATE_CHANNEL not in {"stable", "beta"}:
        errors.append(f"Unsupported UPDATE_CHANNEL: {UPDATE_CHANNEL}")
    is_prerelease = any(marker in VERSION_ID.casefold() for marker in ("alpha", "beta", "rc"))
    expected_channel = "beta" if is_prerelease else "stable"
    if UPDATE_CHANNEL != expected_channel:
        errors.append(f"{VERSION_ID} must use update channel {expected_channel}, got {UPDATE_CHANNEL}")

    release_notes = project_root / "docs" / f"RELEASE-{VERSION_TAG}.md"
    if not release_notes.is_file():
        errors.append(f"Missing release notes: {release_notes.relative_to(project_root)}")
    for required in ("README.md", "LICENSE", "mcw_launcher.spec", "tools/build_release_zip.py"):
        if not (project_root / required).is_file():
            errors.append(f"Missing release file: {required}")
    return errors


def run_preflight(project_root: Path = PROJECT_ROOT) -> list[str]:
    errors: list[str] = []
    errors.extend(audit_version_metadata(project_root))
    errors.extend(audit_private_gateway_bundling(project_root))
    errors.extend(audit_theme_contract(project_root))
    errors.extend(audit_lan_agent(project_root))
    errors.extend(find_merge_markers(project_root))
    errors.extend(audit_language_packs(project_root))
    errors.extend(audit_navigation_translation_keys(project_root))
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate MCW Launcher source before building a release.")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    errors = run_preflight(project_root)
    if errors:
        print("Release preflight failed:")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    translations = load_language_pack(project_root / "lang" / "en-US.json")["translations"]
    print(f"Release preflight passed for {VERSION_TAG} ({UPDATE_CHANNEL}).")
    print(f"Language parity: {len(translations)} keys in en-US and vi-VN.")
    print("Unresolved merge markers: 0")


if __name__ == "__main__":
    main()
