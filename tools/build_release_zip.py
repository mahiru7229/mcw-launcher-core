from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import zipfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import VERSION_ID


DEFAULT_FILES = ("README.md", "LICENSE")
DEFAULT_DIRECTORIES = ("lang", "themes", "docs")
SUPPORTED_PLATFORMS = ("windows-x64", "linux-x64")


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


def validate_platform(platform_id: str) -> str:
    normalized = str(platform_id).strip().casefold()
    if normalized not in SUPPORTED_PLATFORMS:
        raise ValueError(f"Unsupported release platform '{platform_id}'. Expected one of: {', '.join(SUPPORTED_PLATFORMS)}.")
    return normalized


def default_output_path(project_root: Path, version: str, platform_id: str = "windows-x64") -> Path:
    platform_id = validate_platform(platform_id)
    return project_root / "release" / f"MCW-Launcher-v{version}-{platform_id}.zip"


def validate_release_version(version: str, expected_version: str = VERSION_ID) -> str:
    normalized = str(version).strip().removeprefix("v")
    if normalized != expected_version:
        raise ValueError(f"Release version '{normalized}' does not match src.config.VERSION_ID '{expected_version}'.")
    return normalized


def build_release_zip(project_root: Path, executable: Path, version: str, output: Path, platform_id: str = "windows-x64") -> Path:
    if not executable.is_file():
        raise FileNotFoundError(f"Launcher executable not found: {executable}")
    platform_id = validate_platform(platform_id)
    package_name = f"MCW-Launcher-v{version}-{platform_id}"
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="mcw-release-") as temporary:
        payload_root = Path(temporary) / package_name
        payload_root.mkdir(parents=True)
        copy_payload(project_root, payload_root, executable)
        managed_files = sorted(
            path.relative_to(payload_root).as_posix()
            for path in payload_root.rglob("*")
            if path.is_file()
        )
        managed_files.append("mcw-update.json")
        manifest = {
            "schema_version": 1,
            "version": version,
            "platform": platform_id,
            "executable": executable.name,
            "files": sorted(set(managed_files)),
        }
        (payload_root / "mcw-update.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(payload_root.rglob("*")):
                if path.is_file():
                    archive_name = path.relative_to(payload_root.parent).as_posix()
                    info = zipfile.ZipInfo.from_file(path, archive_name)
                    info.compress_type = zipfile.ZIP_DEFLATED
                    if platform_id == "linux-x64" and path == payload_root / executable.name:
                        # A Windows filesystem cannot represent POSIX execute
                        # bits. Encode the Linux launcher contract explicitly
                        # so cross-builds still extract an executable binary.
                        info.create_system = 3
                        info.external_attr = (stat.S_IFREG | 0o755) << 16
                    with path.open("rb") as source, archive.open(info, "w", force_zip64=True) as target:
                        shutil.copyfileobj(source, target, length=1024 * 1024)

    checksum_path = output.with_name(f"{output.name}.sha256")
    # Write bytes so Windows cannot translate the LF terminator to CRLF.
    # The checksum files are later verified together by GNU sha256sum on the
    # Linux publish runner, where a trailing CR becomes part of the filename.
    checksum_path.write_bytes(f"{sha256_file(output)}  {output.name}\n".encode("utf-8"))
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an MCW Launcher ZIP that can be installed by the automatic updater.")
    parser.add_argument("--exe", type=Path, required=True, help="Path to the packaged native launcher executable")
    parser.add_argument("--version", required=True, help=f"Version without a leading v; it must match {VERSION_ID}")
    parser.add_argument("--platform", choices=SUPPORTED_PLATFORMS, default="windows-x64", help="Target platform encoded in the package name and manifest")
    parser.add_argument("--output", type=Path, help="Output ZIP path")
    args = parser.parse_args()

    project_root = PROJECT_ROOT
    try:
        version = validate_release_version(args.version)
        platform_id = validate_platform(args.platform)
    except ValueError as error:
        parser.error(str(error))
    output = args.output or default_output_path(project_root, version, platform_id)
    result = build_release_zip(project_root, args.exe.resolve(), version, output.resolve(), platform_id)
    print(result)
    print(result.with_name(f"{result.name}.sha256"))


if __name__ == "__main__":
    main()
