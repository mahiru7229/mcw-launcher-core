from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import VERSION_ID


DEFAULT_FILES = ("README.md", "LICENSE")
DEFAULT_DIRECTORIES = ("lang", "themes", "docs")


def copy_payload(project_root: Path, payload_root: Path, executable: Path) -> None:
    shutil.copy2(executable, payload_root / executable.name)
    for name in DEFAULT_FILES:
        source = project_root / name
        if source.is_file():
            shutil.copy2(source, payload_root / name)
    for name in DEFAULT_DIRECTORIES:
        source = project_root / name
        if source.is_dir():
            shutil.copytree(source, payload_root / name, dirs_exist_ok=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def default_output_path(project_root: Path, version: str) -> Path:
    return project_root / "release" / f"MCW-Launcher-v{version}-windows-x64.zip"


def validate_release_version(version: str, expected_version: str = VERSION_ID) -> str:
    normalized = str(version).strip().removeprefix("v")
    if normalized != expected_version:
        raise ValueError(f"Release version '{normalized}' does not match src.config.VERSION_ID '{expected_version}'.")
    return normalized


def build_release_zip(project_root: Path, executable: Path, version: str, output: Path) -> Path:
    if not executable.is_file():
        raise FileNotFoundError(f"Launcher executable not found: {executable}")
    package_name = f"MCW-Launcher-v{version}-windows-x64"
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="mcw-release-") as temporary:
        payload_root = Path(temporary) / package_name
        payload_root.mkdir(parents=True)
        copy_payload(project_root, payload_root, executable)
        manifest = {
            "schema_version": 1,
            "version": version,
            "platform": "windows-x64",
            "executable": executable.name,
        }
        (payload_root / "mcw-update.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(payload_root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(payload_root.parent).as_posix())

    checksum_path = output.with_name(f"{output.name}.sha256")
    checksum_path.write_text(f"{sha256_file(output)}  {output.name}\n", encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an MCW Launcher ZIP that can be installed by the automatic updater.")
    parser.add_argument("--exe", type=Path, required=True, help="Path to the packaged MCW Launcher.exe")
    parser.add_argument("--version", required=True, help=f"Version without a leading v; it must match {VERSION_ID}")
    parser.add_argument("--output", type=Path, help="Output ZIP path")
    args = parser.parse_args()

    project_root = PROJECT_ROOT
    try:
        version = validate_release_version(args.version)
    except ValueError as error:
        parser.error(str(error))
    output = args.output or default_output_path(project_root, version)
    result = build_release_zip(project_root, args.exe.resolve(), version, output.resolve())
    print(result)
    print(result.with_name(f"{result.name}.sha256"))


if __name__ == "__main__":
    main()
