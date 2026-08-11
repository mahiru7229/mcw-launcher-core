from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from uuid import uuid4
import zipfile

from src.core.theme.theme_contract import MAX_THEME_ARCHIVE_BYTES, MAX_THEME_ARCHIVE_FILES, THEME_ID_PATTERN
from src.core.theme.theme_manager import ThemeDefinition, ThemeManager, theme_manager
from src.core.theme.theme_package import CHECKSUM_FILENAME, ThemePackage, ThemePackageError
from src.core.theme.theme_validation import ThemeValidationIssue, ThemeValidationReport, ThemeValidator


class ThemeAuthoringError(RuntimeError):
    def __init__(self, message: str, code: str = "THEME_AUTHORING_ERROR") -> None:
        super().__init__(message)
        self.code = code


class ThemeAuthoringService:
    THEME_ID_PATTERN = THEME_ID_PATTERN
    MAX_ARCHIVE_FILES = MAX_THEME_ARCHIVE_FILES
    MAX_ARCHIVE_BYTES = MAX_THEME_ARCHIVE_BYTES
    ALLOWED_EXTENSIONS = frozenset({".json", ".png", ".ttf", ".otf", ".qss", ".md", ".txt", ".license"})
    ALLOWED_EXTENSIONLESS_NAMES = frozenset({"license", "copying", "notice"})
    EXCLUDED_NAMES = frozenset({"__pycache__", ".git", ".svn", ".hg"})

    def __init__(self, manager: ThemeManager | None = None) -> None:
        self.manager = manager or theme_manager
        self.validator = ThemeValidator(self.manager)

    def validate(self, theme_id: str) -> ThemeValidationReport:
        return self.validator.validate(theme_id)

    def validate_directory(self, root: Path) -> ThemeValidationReport:
        return self.validator.validate_directory(root)

    def duplicate(self, theme_id: str, new_id: str, new_name: str | None = None) -> ThemeDefinition:
        source = self._require_editable_theme(theme_id)
        normalized_id = self._normalize_theme_id(new_id)
        destination = (self.manager.root / normalized_id).resolve()
        self._ensure_inside_root(destination)
        if destination.exists():
            raise ThemeAuthoringError(f"Theme already exists: {normalized_id}", "THEME_DUPLICATE_ID")
        self._copy_theme_tree(source.root, destination)
        try:
            manifest_path = destination / self.manager.MANIFEST_NAME
            payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            payload["id"] = normalized_id
            payload["name"] = str(new_name or payload.get("name") or normalized_id).strip() or normalized_id
            manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            # A duplicated theme is a source tree, not an exported package. Remove
            # stale package metadata so subsequent edits do not produce false
            # checksum failures.
            (destination / CHECKSUM_FILENAME).unlink(missing_ok=True)
            report = self.validate_directory(destination)
            if not report.is_valid:
                raise ThemeAuthoringError(
                    "Duplicated theme failed validation: " + "; ".join(issue.message for issue in report.issues),
                    "THEME_DUPLICATE_VALIDATION_FAILED",
                )
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            raise
        self.manager.reload()
        return self._require_theme(normalized_id)

    def export(self, theme_id: str, destination: Path) -> Path:
        definition = self._require_editable_theme(theme_id)
        report = self.validate(theme_id)
        if not report.is_valid:
            raise ThemeAuthoringError("Theme contains validation errors and cannot be exported.", "THEME_EXPORT_VALIDATION_FAILED")
        output = Path(destination)
        if output.suffix.lower() != ".zip":
            output = output.with_suffix(".zip")
        entries = self._theme_files(definition.root)
        return ThemePackage.write_deterministic_zip(output, definition.theme_id, entries)

    def import_archive(self, archive_path: Path, overwrite: bool = False) -> ThemeDefinition:
        source = Path(archive_path)
        if not source.is_file():
            raise ThemeAuthoringError(f"Theme archive does not exist: {source}", "THEME_PACKAGE_NOT_FOUND")
        self.manager.root.mkdir(parents=True, exist_ok=True)
        staging_root: Path | None = Path(tempfile.mkdtemp(prefix=".theme-import-", dir=self.manager.root))
        try:
            with zipfile.ZipFile(source) as archive:
                members = self._validated_archive_members(archive)
                prefix = self._archive_theme_prefix(members)
                for member in members:
                    relative = PurePosixPath(member.filename.replace("\\", "/"))
                    if prefix:
                        relative = PurePosixPath(*relative.parts[1:])
                    if not relative.parts:
                        continue
                    destination = staging_root.joinpath(*relative.parts)
                    ThemePackage.copy_member(archive, member, destination)
            checksum_report = ThemePackage.verify_directory_checksums(staging_root)
            report = self.validate_directory(staging_root)
            if checksum_report is not None and checksum_report.theme_id and checksum_report.theme_id != report.theme_id:
                raise ThemeAuthoringError(
                    f"Theme package ID mismatch: checksums declare {checksum_report.theme_id}, manifest declares {report.theme_id}.",
                    "THEME_PACKAGE_ID_MISMATCH",
                )
            if not report.is_valid:
                raise ThemeAuthoringError(
                    "Imported theme failed validation: " + "; ".join(issue.message for issue in report.issues),
                    "THEME_IMPORT_VALIDATION_FAILED",
                )
            normalized_id = self._normalize_theme_id(report.theme_id)
            destination = (self.manager.root / normalized_id).resolve()
            self._ensure_inside_root(destination)
            backup: Path | None = None
            if destination.exists():
                if not overwrite:
                    raise ThemeAuthoringError(f"Theme already exists: {normalized_id}", "THEME_IMPORT_ALREADY_EXISTS")
                backup = self.manager.root / f".theme-backup-{normalized_id}-{uuid4().hex}"
                destination.replace(backup)
            try:
                staging_root.replace(destination)
            except OSError:
                if backup is not None and backup.exists() and not destination.exists():
                    backup.replace(destination)
                raise
            staging_root = None
            if backup is not None:
                shutil.rmtree(backup, ignore_errors=True)
            self.manager.reload()
            return self._require_theme(normalized_id)
        except ThemePackageError as error:
            raise ThemeAuthoringError(str(error), error.code) from error
        except (OSError, zipfile.BadZipFile) as error:
            raise ThemeAuthoringError(f"Unable to import theme archive: {error}", "THEME_PACKAGE_READ_FAILED") from error
        finally:
            if staging_root is not None and staging_root.exists():
                shutil.rmtree(staging_root, ignore_errors=True)

    def _validated_archive_members(self, archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
        members = [member for member in archive.infolist() if not member.is_dir()]
        if not members or len(members) > self.MAX_ARCHIVE_FILES:
            raise ThemeAuthoringError("Theme archive has an invalid number of files.", "THEME_PACKAGE_FILE_COUNT_INVALID")
        total_bytes = 0
        names: set[str] = set()
        for member in members:
            if member.flag_bits & 0x1:
                raise ThemeAuthoringError("Encrypted theme archives are not supported.", "THEME_PACKAGE_ENCRYPTED")
            if ThemePackage.is_symlink(member):
                raise ThemeAuthoringError("Theme archives may not contain symbolic links.", "THEME_PACKAGE_SYMLINK")
            path = PurePosixPath(member.filename.replace("\\", "/"))
            normalized_name = path.as_posix().casefold()
            if normalized_name in names:
                raise ThemeAuthoringError(f"Duplicate path in theme archive: {member.filename}", "THEME_PACKAGE_DUPLICATE_PATH")
            names.add(normalized_name)
            if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
                raise ThemeAuthoringError(f"Unsafe path in theme archive: {member.filename}", "THEME_PACKAGE_PATH_UNSAFE")
            if any(part in self.EXCLUDED_NAMES for part in path.parts):
                raise ThemeAuthoringError(f"Disallowed directory in theme archive: {member.filename}", "THEME_PACKAGE_DIRECTORY_DISALLOWED")
            suffix = path.suffix.lower()
            if suffix not in self.ALLOWED_EXTENSIONS and path.name.casefold() not in self.ALLOWED_EXTENSIONLESS_NAMES:
                raise ThemeAuthoringError(f"Unsupported file type in theme archive: {member.filename}", "THEME_PACKAGE_FILE_TYPE_UNSUPPORTED")
            total_bytes += int(member.file_size)
            if total_bytes > self.MAX_ARCHIVE_BYTES:
                raise ThemeAuthoringError("Theme archive exceeds the uncompressed size limit.", "THEME_PACKAGE_SIZE_LIMIT")
        return members

    @staticmethod
    def _archive_theme_prefix(members: list[zipfile.ZipInfo]) -> str:
        paths = [PurePosixPath(member.filename.replace("\\", "/")) for member in members]
        root_manifest = any(path == PurePosixPath("theme.json") for path in paths)
        if root_manifest:
            return ""
        top_levels = {path.parts[0] for path in paths if path.parts}
        if len(top_levels) != 1:
            raise ThemeAuthoringError("Theme archive must contain one theme folder or a root theme.json.", "THEME_PACKAGE_ROOT_INVALID")
        prefix = next(iter(top_levels))
        if PurePosixPath(prefix, "theme.json") not in paths:
            raise ThemeAuthoringError("Theme archive does not contain theme.json.", "THEME_PACKAGE_MANIFEST_MISSING")
        return prefix

    def _theme_files(self, root: Path) -> list[tuple[Path, str]]:
        files: list[tuple[Path, str]] = []
        total_bytes = 0
        for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix().casefold()):
            relative = path.relative_to(root)
            if any(part in self.EXCLUDED_NAMES for part in relative.parts) or path.is_symlink() or not path.is_file():
                continue
            if path.name == CHECKSUM_FILENAME or path.name.endswith((".tmp", ".bak")) or path.suffix.lower() in {".py", ".pyc", ".exe", ".dll", ".bat", ".cmd", ".ps1", ".js"}:
                continue
            suffix = path.suffix.lower()
            if suffix not in self.ALLOWED_EXTENSIONS and path.name.casefold() not in self.ALLOWED_EXTENSIONLESS_NAMES:
                continue
            total_bytes += path.stat().st_size
            if len(files) >= self.MAX_ARCHIVE_FILES or total_bytes > self.MAX_ARCHIVE_BYTES:
                raise ThemeAuthoringError("Theme exceeds export limits.", "THEME_EXPORT_LIMIT")
            files.append((path, relative.as_posix()))
        return files

    def _copy_theme_tree(self, source: Path | None, destination: Path) -> None:
        if source is None:
            raise ThemeAuthoringError("Built-in CSS fallback cannot be duplicated.", "THEME_DUPLICATE_BUILTIN")
        for path in source.rglob("*"):
            if path.is_symlink():
                raise ThemeAuthoringError("Themes containing symbolic links cannot be duplicated.", "THEME_DUPLICATE_SYMLINK")
        shutil.copytree(source, destination)

    def _require_editable_theme(self, theme_id: str) -> ThemeDefinition:
        definition = self._require_theme(theme_id)
        if definition.root is None:
            raise ThemeAuthoringError("Built-in CSS fallback does not have an editable theme folder.", "THEME_BUILTIN_NOT_EDITABLE")
        return definition

    def _require_theme(self, theme_id: str) -> ThemeDefinition:
        definition = self._definition(theme_id)
        if definition is None:
            raise ThemeAuthoringError(f"Theme is not installed: {theme_id}", "THEME_NOT_INSTALLED")
        return definition

    def _definition(self, theme_id: str) -> ThemeDefinition | None:
        normalized = str(theme_id or "").strip()
        return next((theme for theme in self.manager.available_themes() if theme.theme_id == normalized), None)

    def _normalize_theme_id(self, value: str) -> str:
        normalized = str(value or "").strip().lower().replace(" ", "-")
        if not self.THEME_ID_PATTERN.fullmatch(normalized):
            raise ThemeAuthoringError(
                "Theme ID must use lowercase letters, numbers, dots, underscores, or hyphens.",
                "THEME_ID_INVALID",
            )
        return normalized

    def _ensure_inside_root(self, path: Path) -> None:
        try:
            path.relative_to(self.manager.root.resolve())
        except ValueError as error:
            raise ThemeAuthoringError("Theme path escapes the theme root.", "THEME_PATH_OUTSIDE_ROOT") from error

    @classmethod
    def _detail(cls, message: str) -> ThemeValidationIssue:
        return ThemeValidator.issue_from_message(message)

    @staticmethod
    def _category(message: str) -> str:
        return ThemeValidator.issue_from_message(message).category
