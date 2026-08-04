from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import zipfile

from src.core.theme.theme_contract import THEME_PACKAGE_FORMAT_VERSION, canonical_json_bytes, pretty_json_text

CHECKSUM_FILENAME = "theme-checksums.json"
_FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


class ThemePackageError(RuntimeError):
    def __init__(self, message: str, code: str = "THEME_PACKAGE_INVALID") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ThemePackageChecksumReport:
    theme_id: str
    files: dict[str, str]
    package_format_version: int = THEME_PACKAGE_FORMAT_VERSION
    algorithm: str = "sha256"

    def to_dict(self) -> dict[str, object]:
        return {
            "package_format_version": self.package_format_version,
            "theme_id": self.theme_id,
            "algorithm": self.algorithm,
            "files": dict(sorted(self.files.items())),
        }


class ThemePackage:
    @staticmethod
    def sha256_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @classmethod
    def checksum_report(cls, theme_id: str, entries: list[tuple[Path, str]]) -> ThemePackageChecksumReport:
        return ThemePackageChecksumReport(theme_id, {relative: cls.sha256_bytes(path.read_bytes()) for path, relative in entries})

    @classmethod
    def write_deterministic_zip(cls, output: Path, theme_id: str, entries: list[tuple[Path, str]]) -> Path:
        destination = Path(output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        report = cls.checksum_report(theme_id, entries)
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path, relative in sorted(entries, key=lambda item: item[1]):
                cls._write_entry(archive, f"{theme_id}/{relative}", path.read_bytes())
            cls._write_entry(archive, f"{theme_id}/{CHECKSUM_FILENAME}", pretty_json_text(report.to_dict()).encode("utf-8"))
        return destination

    @classmethod
    def verify_directory_checksums(cls, root: Path) -> ThemePackageChecksumReport | None:
        directory = Path(root)
        checksum_path = directory / CHECKSUM_FILENAME
        if not checksum_path.is_file():
            return None
        try:
            payload = json.loads(checksum_path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ThemePackageError(f"Unable to read {CHECKSUM_FILENAME}: {error}", "THEME_PACKAGE_CHECKSUM_MANIFEST_INVALID") from error
        if not isinstance(payload, dict):
            raise ThemePackageError(f"{CHECKSUM_FILENAME} root must be an object.", "THEME_PACKAGE_CHECKSUM_MANIFEST_INVALID")
        try:
            format_version = int(payload.get("package_format_version", 0))
        except (TypeError, ValueError) as error:
            raise ThemePackageError("Theme package format version must be an integer.", "THEME_PACKAGE_FORMAT_VERSION_INVALID") from error
        if format_version not in {0, THEME_PACKAGE_FORMAT_VERSION}:
            raise ThemePackageError(f"Unsupported theme package format version: {format_version}", "THEME_PACKAGE_FORMAT_VERSION_UNSUPPORTED")
        files = payload.get("files")
        # Beta 2 wrote the map under `sha256`; keep that package format importable.
        if files is None:
            files = payload.get("sha256")
        if not isinstance(files, dict):
            raise ThemePackageError(f"{CHECKSUM_FILENAME} does not contain a checksum map.", "THEME_PACKAGE_CHECKSUM_MANIFEST_INVALID")
        algorithm = str(payload.get("algorithm", "sha256")).casefold()
        if algorithm != "sha256":
            raise ThemePackageError(f"Unsupported theme checksum algorithm: {algorithm}", "THEME_PACKAGE_CHECKSUM_ALGORITHM_UNSUPPORTED")

        normalized_expected: dict[str, str] = {}
        for relative, expected in sorted(files.items()):
            safe_relative = cls._safe_checksum_relative_path(str(relative))
            key = safe_relative.as_posix()
            if key.casefold() in {name.casefold() for name in normalized_expected}:
                raise ThemePackageError(f"Duplicate checksum path: {key}", "THEME_PACKAGE_CHECKSUM_DUPLICATE_PATH")
            normalized_expected[key] = str(expected).strip().casefold()

        actual_files: dict[str, Path] = {}
        for candidate in sorted(directory.rglob("*")):
            if not candidate.is_file() or candidate == checksum_path:
                continue
            relative = candidate.relative_to(directory).as_posix()
            actual_files[relative] = candidate
        expected_names = set(normalized_expected)
        actual_names = set(actual_files)
        missing = sorted(expected_names - actual_names)
        extra = sorted(actual_names - expected_names)
        if missing:
            raise ThemePackageError(f"Theme package checksum file is missing: {missing[0]}", "THEME_PACKAGE_CHECKSUM_FILE_MISSING")
        if extra:
            raise ThemePackageError(f"Theme package contains an unchecked file: {extra[0]}", "THEME_PACKAGE_CHECKSUM_EXTRA_FILE")

        for relative, expected in normalized_expected.items():
            actual = cls.sha256_bytes(actual_files[relative].read_bytes())
            if actual.casefold() != expected:
                raise ThemePackageError(f"Theme package checksum mismatch: {relative}", "THEME_PACKAGE_CHECKSUM_MISMATCH")
        return ThemePackageChecksumReport(
            theme_id=str(payload.get("theme_id") or "").strip(),
            files=normalized_expected,
            package_format_version=THEME_PACKAGE_FORMAT_VERSION if format_version == 0 else format_version,
            algorithm=algorithm,
        )

    @staticmethod
    def copy_member(archive: zipfile.ZipFile, member: zipfile.ZipInfo, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as input_file, destination.open("wb") as output_file:
            shutil.copyfileobj(input_file, output_file)

    @staticmethod
    def is_symlink(member: zipfile.ZipInfo) -> bool:
        return stat.S_ISLNK(member.external_attr >> 16)

    @staticmethod
    def _safe_checksum_relative_path(value: str) -> PurePosixPath:
        path = PurePosixPath(value.replace("\\", "/"))
        if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
            raise ThemePackageError(f"Unsafe path in {CHECKSUM_FILENAME}: {value}", "THEME_PACKAGE_CHECKSUM_PATH_UNSAFE")
        if path.name == CHECKSUM_FILENAME:
            raise ThemePackageError(f"{CHECKSUM_FILENAME} may not checksum itself.", "THEME_PACKAGE_CHECKSUM_SELF_REFERENCE")
        return path

    @staticmethod
    def _write_entry(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
        info = zipfile.ZipInfo(PurePosixPath(name).as_posix(), date_time=_FIXED_ZIP_TIMESTAMP)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.create_system = 3
        info.external_attr = (0o100644 & 0xFFFF) << 16
        info.flag_bits |= 0x800
        archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
