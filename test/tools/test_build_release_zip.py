from pathlib import Path
import json
import subprocess
import sys
import zipfile

import pytest

from src.config import VERSION_ID
from tools.build_release_zip import build_release_zip, validate_release_version


def test_validate_release_version_accepts_current_release() -> None:
    assert validate_release_version(f"v{VERSION_ID}") == VERSION_ID


def test_validate_release_version_rejects_mismatch() -> None:
    with pytest.raises(ValueError, match="does not match"):
        validate_release_version("0.5.1")


def test_build_release_zip_writes_update_manifest(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "README.md").write_text("readme", encoding="utf-8")
    (project / "LICENSE").write_text("license", encoding="utf-8")
    for directory in ("lang", "themes", "docs"):
        (project / directory).mkdir()
        (project / directory / "keep.txt").write_text(directory, encoding="utf-8")
    executable = tmp_path / "MCW Launcher.exe"
    executable.write_bytes(b"fake-exe")
    output = project / "release" / f"MCW-Launcher-v{VERSION_ID}-windows-x64.zip"

    build_release_zip(project, executable, VERSION_ID, output)

    with zipfile.ZipFile(output) as archive:
        root = f"MCW-Launcher-v{VERSION_ID}-windows-x64"
        manifest = json.loads(archive.read(f"{root}/mcw-update.json"))
        assert manifest["version"] == VERSION_ID
        assert f"{root}/MCW Launcher.exe" in archive.namelist()
    assert output.with_name(f"{output.name}.sha256").is_file()


def test_release_script_runs_directly_from_any_working_directory(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    executable = tmp_path / "MCW Launcher.exe"
    executable.write_bytes(b"fake-exe")
    output = tmp_path / f"MCW-Launcher-v{VERSION_ID}-windows-x64.zip"

    result = subprocess.run([sys.executable, str(project_root / "tools" / "build_release_zip.py"), "--exe", str(executable), "--version", VERSION_ID, "--output", str(output)], cwd=tmp_path, capture_output=True, text=True, timeout=30)

    assert result.returncode == 0, result.stderr
    assert output.is_file()
    assert output.with_name(f"{output.name}.sha256").is_file()
