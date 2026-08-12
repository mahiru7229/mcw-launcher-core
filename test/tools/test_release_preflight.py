from __future__ import annotations

import json
from pathlib import Path

from src.config import VERSION_TAG
import tools.release_preflight as release_preflight
from tools.release_preflight import audit_gui_core_boundary, audit_language_packs, audit_launcher_icon, audit_private_gateway_bundling, audit_release_evidence, audit_theme_contract, find_merge_markers


def write_pack(path: Path, locale: str, translations: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "meta": {"locale": locale, "name": locale, "version": 1},
                "translations": translations,
                "aliases": {},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def test_find_merge_markers_reports_release_text_files(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("before\n<<<<<<< HEAD\nafter\n", encoding="utf-8")
    errors = find_merge_markers(tmp_path)
    assert errors == ["README.md:2: unresolved merge marker"]


def test_language_audit_accepts_matching_keys_and_placeholders(tmp_path: Path) -> None:
    translations = {"hello": "Hello", "welcome": "Welcome {name}"}
    write_pack(tmp_path / "lang" / "en-US.json", "en-US", translations)
    write_pack(tmp_path / "lang" / "vi-VN.json", "vi-VN", {"hello": "Xin chào", "welcome": "Chào mừng {name}"})
    assert audit_language_packs(tmp_path) == []


def test_language_audit_reports_missing_keys_and_placeholder_mismatch(tmp_path: Path) -> None:
    write_pack(tmp_path / "lang" / "en-US.json", "en-US", {"welcome": "Welcome {name}", "missing": "Missing"})
    write_pack(tmp_path / "lang" / "vi-VN.json", "vi-VN", {"welcome": "Chào mừng {username}"})
    errors = audit_language_packs(tmp_path)
    assert "vi-VN is missing translation key: missing" in errors
    assert any(error.startswith("Placeholder mismatch for welcome:") for error in errors)


def test_current_release_notes_exist() -> None:
    project_root = Path(__file__).resolve().parents[2]
    assert (project_root / "docs" / f"RELEASE-{VERSION_TAG}.md").is_file()


def test_private_gateway_audit_rejects_unexpected_or_secret_configuration(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "config.py").write_text(
        'CURSEFORGE_GATEWAY_URL = "https://private.example/api/curseforge"\n'
        'CURSEFORGE_DEFAULT_GATEWAY_URL = "https://private.example/api/curseforge"\n'
        'CURSEFORGE_API_KEY = "secret"\n',
        encoding="utf-8",
    )
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "curseforge.example.json").write_text(
        json.dumps({
            "default_gateway_url": "https://private.example/api/curseforge",
            "bundled_gateway_urls": ["https://another-private.example/api/curseforge"],
        }),
        encoding="utf-8",
    )
    (tmp_path / ".gitignore").write_text("", encoding="utf-8")

    errors = audit_private_gateway_bundling(tmp_path)

    assert any("Legacy CurseForge gateway constants" in error for error in errors)
    assert "src/config.py must not bundle a default CurseForge gateway URL" in errors
    assert "CurseForge API credentials must not be bundled in src/config.py" in errors
    assert "config/curseforge.example.json must not document a bundled default gateway URL" in errors
    assert "config/curseforge.example.json must not contain bundled gateway URLs" in errors
    assert ".gitignore must exclude config/private/" in errors


def test_private_gateway_audit_accepts_no_bundled_default(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "config.py").write_text(
        'CURSEFORGE_DEFAULT_GATEWAY_URL = ""\n',
        encoding="utf-8",
    )
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "curseforge.example.json").write_text(
        json.dumps({"default_gateway_url": "", "bundled_gateway_urls": []}),
        encoding="utf-8",
    )
    (tmp_path / ".gitignore").write_text("config/private/\n", encoding="utf-8")

    # The audit also validates the already-imported release configuration.
    # Isolate that process-level value so this temporary-project fixture is
    # deterministic even when another test or local checkout imported an older
    # src.config module earlier in the pytest session.
    monkeypatch.setattr(release_preflight, "CURSEFORGE_DEFAULT_GATEWAY_URL", "")

    assert audit_private_gateway_bundling(tmp_path) == []


def test_current_theme_contract_audit_passes() -> None:
    project_root = Path(__file__).resolve().parents[2]
    assert audit_theme_contract(project_root) == []


def test_current_launcher_icon_audit_passes() -> None:
    project_root = Path(__file__).resolve().parents[2]
    assert audit_launcher_icon(project_root) == []


def test_launcher_icon_audit_reports_missing_assets(tmp_path: Path) -> None:
    (tmp_path / "mcw_launcher.spec").write_text("# missing icon config\n", encoding="utf-8")
    (tmp_path / "src" / "gui").mkdir(parents=True)
    (tmp_path / "src" / "gui" / "application.py").write_text("# missing window icon\n", encoding="utf-8")
    errors = audit_launcher_icon(tmp_path)
    normalized_errors = [error.replace("\\", "/") for error in errors]
    assert "Missing launcher icon asset: assets/icons/mcw_launcher.ico" in normalized_errors
    assert "Missing launcher icon asset: assets/icons/mcw_launcher.png" in normalized_errors
    assert "mcw_launcher.spec does not configure the Windows executable icon" in errors
    assert "QApplication does not configure the launcher window icon" in errors


def test_release_evidence_rejects_stale_version(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(release_preflight, "VERSION_ID", "1.3.2")
    (tmp_path / "TEST-RESULTS.txt").write_text("mcw-core 1.3.1\n", encoding="utf-8")
    (tmp_path / "CHANGES.diff").write_text("diff for 1.3.1\n", encoding="utf-8")

    errors = audit_release_evidence(tmp_path)

    assert "TEST-RESULTS.txt does not reference current version 1.3.2" in errors
    assert "CHANGES.diff does not reference current version 1.3.2" in errors


def test_gui_core_boundary_rejects_direct_src_core_import(tmp_path: Path) -> None:
    gui = tmp_path / "src" / "gui"
    gui.mkdir(parents=True)
    (gui / "bad.py").write_text("from src.core.foo import Bar\n", encoding="utf-8")

    errors = [error.replace("\\", "/") for error in audit_gui_core_boundary(tmp_path)]
    assert errors == ["src/gui/bad.py:1: GUI must not import src.core directly"]
