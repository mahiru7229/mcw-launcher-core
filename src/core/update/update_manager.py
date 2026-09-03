from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import uuid
import zipfile

import httpx

from src.core.fs.paths import Paths
from src.core.network.download_bandwidth_limiter import download_bandwidth_limiter  # shared singleton; compatibility export
from src.core.network.download_manager import download_manager
from src.core.network.download_models import DownloadRequest
from src.core.network.httpx_downloader import HttpDownloader
from src.core.progress.progress_reporter import ProgressReporter
from src.core.system.platform_info import PlatformInfo
from src.core.update.github_release_client import GitHubReleaseClient
from src.core.update.versioning import LauncherVersion
from src.models.update.update_info import PreparedUpdate, UpdateInfo
from src.models.progress.progress_stage import ProgressStage


class UpdateManager:
    MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024
    MAX_EXTRACTED_BYTES = 4 * 1024 * 1024 * 1024
    MAX_ARCHIVE_ENTRIES = 20_000
    PACKAGE_MANIFEST_NAME = "mcw-update.json"
    PACKAGE_MANIFEST_SCHEMA_VERSION = 1

    def __init__(
        self,
        repository: str,
        current_version: str,
        channel: str = "stable",
        platform_id: str | None = None,
    ) -> None:
        self.platform_id = platform_id or self._current_platform_id()
        self.client = GitHubReleaseClient(
            repository=repository,
            current_version=current_version,
            channel=channel,
            platform_id=self.platform_id,
        )

    def check_for_update(self, force_refresh: bool = False) -> UpdateInfo | None:
        return self.client.check(force_refresh=force_refresh)

    def prepare_update(self, info: UpdateInfo, reporter: ProgressReporter | None = None) -> PreparedUpdate:
        archive_path = Paths.update_download_path(info.tag_name, info.asset.name)
        self._download_archive(info, archive_path, reporter)

        staging_directory = Paths.update_staging_root() / f"{self._safe_name(info.tag_name)}-{uuid.uuid4().hex}"
        extraction_directory = staging_directory / "extracted"
        try:
            if reporter is not None:
                reporter.status(stage=ProgressStage.DOWNLOADING_UPDATE, message="Extracting launcher update...")
            extraction_directory.mkdir(parents=True, exist_ok=False)
            self._extract_archive(archive_path, extraction_directory)
            content_directory = self._resolve_content_directory(extraction_directory)
            if not any(content_directory.iterdir()):
                raise RuntimeError("The update archive does not contain any files.")
            self._validate_package_manifest(content_directory, info)
            return PreparedUpdate(info=info, archive_path=archive_path, staging_directory=staging_directory, content_directory=content_directory)
        except Exception:
            shutil.rmtree(staging_directory, ignore_errors=True)
            raise


    def _validate_package_manifest(self, content_directory: Path, info: UpdateInfo) -> None:
        manifest_path = content_directory / self.PACKAGE_MANIFEST_NAME
        if not manifest_path.is_file():
            raise RuntimeError(f"The update package is missing {self.PACKAGE_MANIFEST_NAME}.")
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Invalid {cls.PACKAGE_MANIFEST_NAME}: {error}") from error
        if not isinstance(payload, dict):
            raise RuntimeError(f"{cls.PACKAGE_MANIFEST_NAME} must contain a JSON object.")
        if int(payload.get("schema_version", 0) or 0) != self.PACKAGE_MANIFEST_SCHEMA_VERSION:
            raise RuntimeError(f"Unsupported update package schema: {payload.get('schema_version')}")
        package_platform = str(payload.get("platform") or "").strip().casefold()
        if package_platform != self.platform_id:
            raise RuntimeError(
                f"Update package platform mismatch: expected {self.platform_id}, found {package_platform or 'missing'}."
            )
        package_version = str(payload.get("version") or "").strip()
        if not package_version:
            raise RuntimeError("The update package manifest does not declare a version.")
        try:
            expected = LauncherVersion.parse(info.version)
            actual = LauncherVersion.parse(package_version)
        except ValueError as error:
            raise RuntimeError(f"The update package contains an invalid version: {package_version}") from error
        if actual != expected:
            raise RuntimeError(f"Update package version mismatch: expected {expected}, found {actual}.")
        executable_name = str(payload.get("executable") or "").strip()
        if Path(executable_name).name != executable_name or not executable_name:
            raise RuntimeError("The update package manifest contains an invalid executable name.")
        if self.platform_id == "windows-x64" and not executable_name.casefold().endswith(".exe"):
            raise RuntimeError("The Windows update package must declare an .exe launcher.")
        if self.platform_id == "linux-x64" and executable_name.casefold().endswith(".exe"):
            raise RuntimeError("The Linux update package declares a Windows executable.")
        if not (content_directory / executable_name).is_file():
            raise RuntimeError(f"The update package does not contain the declared executable: {executable_name}")
        managed_files = payload.get("files")
        if not isinstance(managed_files, list) or not managed_files:
            raise RuntimeError("The update package manifest does not declare its managed files.")
        normalized_files: set[str] = set()
        normalized_file_keys: set[str] = set()
        for raw_path in managed_files:
            relative = self._safe_archive_path(str(raw_path or ""))
            if relative is None:
                raise RuntimeError("The update package manifest contains an invalid managed file path.")
            normalized = relative.as_posix()
            normalized_key = normalized.casefold()
            if normalized_key in normalized_file_keys:
                raise RuntimeError(f"The update package manifest contains a duplicate managed file path: {normalized}")
            normalized_files.add(normalized)
            normalized_file_keys.add(normalized_key)
            if not (content_directory / Path(*relative.parts)).is_file():
                raise RuntimeError(f"The update package is missing a managed file: {normalized}")
        if self.PACKAGE_MANIFEST_NAME not in normalized_files:
            raise RuntimeError(f"The update package manifest must list {self.PACKAGE_MANIFEST_NAME} as a managed file.")
        if executable_name not in normalized_files:
            raise RuntimeError("The update package manifest must list its launcher executable as a managed file.")
        actual_files = {
            path.relative_to(content_directory).as_posix()
            for path in content_directory.rglob("*")
            if path.is_file()
        }
        undeclared_files = sorted(actual_files.difference(normalized_files), key=str.casefold)
        if undeclared_files:
            raise RuntimeError(
                f"The update package contains an undeclared file: {undeclared_files[0]}"
            )
        if self.platform_id == "linux-x64":
            executable_mode = (content_directory / executable_name).stat().st_mode
            if executable_mode & 0o111 == 0:
                raise RuntimeError("The Linux launcher in the update package is not executable.")

    def _download_archive(self, info: UpdateInfo, archive_path: Path, reporter: ProgressReporter | None = None, max_retry: int = 3) -> None:
        expected_sha256 = self._resolve_expected_sha256(info)
        if archive_path.is_file() and self._archive_matches(archive_path, info.asset.size, expected_sha256):
            size = info.asset.size if info.asset.size > 0 else archive_path.stat().st_size
            if reporter is not None:
                reporter.bytes(stage=ProgressStage.DOWNLOADING_UPDATE, message="Using cached launcher update...", current=size, total=size)
            return

        request = DownloadRequest(
            urls=(info.asset.download_url,),
            destination=archive_path,
            expected_size=max(0, int(info.asset.size or 0)),
            hashes={"sha256": expected_sha256},
            source="launcher_update",
            display_name=info.asset.name or archive_path.name,
            max_attempts=max_retry,
            timeout=httpx.Timeout(connect=20.0, read=120.0, write=30.0, pool=30.0),
            headers={"User-Agent": f"mahiru7229/mcw-launcher/{info.current_version}"},
            allow_unverified=False,
            max_bytes=self.MAX_ARCHIVE_BYTES,
            operation_id=f"launcher-update:{info.version}",
        )
        download_manager.download(
            request,
            reporter=reporter,
            progress_stage=ProgressStage.DOWNLOADING_UPDATE,
            progress_message=f"Downloading launcher update {info.version}...",
            client_provider=HttpDownloader.get_client,
        )
        if not self._archive_matches(archive_path, info.asset.size, expected_sha256):
            archive_path.unlink(missing_ok=True)
            raise RuntimeError("The downloaded launcher update archive failed validation.")


    @staticmethod
    def _valid_sha256(value: str) -> bool:
        normalized = str(value or "").strip().casefold()
        return len(normalized) == 64 and all(character in "0123456789abcdef" for character in normalized)

    def _resolve_expected_sha256(self, info: UpdateInfo) -> str:
        direct = str(info.asset.sha256 or "").strip().casefold()
        if self._valid_sha256(direct):
            return direct

        checksum_url = str(info.asset.sha256_url or "").strip()
        if not checksum_url.startswith("https://"):
            raise RuntimeError("Automatic launcher updates require a trusted SHA-256 digest or .sha256 release asset.")

        response = HttpDownloader.get_client().get(
            checksum_url,
            headers={"User-Agent": f"mahiru7229/mcw-launcher/{info.current_version}"},
            timeout=15.0,
        )
        response.raise_for_status()
        if len(response.content) > 4096:
            raise RuntimeError("The launcher update checksum file is unexpectedly large.")
        first_line = response.text.lstrip("\ufeff").strip().splitlines()[0] if response.text.strip() else ""
        candidate = first_line.split()[0].strip().casefold() if first_line else ""
        if not self._valid_sha256(candidate):
            raise RuntimeError("The launcher update checksum file does not contain a valid SHA-256 digest.")
        return candidate

    @staticmethod
    def _response_size(response: httpx.Response) -> int:
        try:
            return max(0, int(response.headers.get("Content-Length", 0) or 0))
        except ValueError:
            return 0

    @staticmethod
    def _archive_matches(path: Path, expected_size: int, expected_sha256: str | None) -> bool:
        try:
            if expected_size > 0 and path.stat().st_size != expected_size:
                return False
            if expected_sha256 is None:
                return zipfile.is_zipfile(path)
            sha256 = hashlib.sha256()
            with path.open("rb") as file:
                while chunk := file.read(1024 * 1024):
                    sha256.update(chunk)
            return sha256.hexdigest().lower() == expected_sha256.lower()
        except OSError:
            return False

    def _extract_archive(self, archive_path: Path, destination: Path) -> None:
        with zipfile.ZipFile(archive_path) as archive:
            entries = archive.infolist()
            if len(entries) > self.MAX_ARCHIVE_ENTRIES:
                raise RuntimeError("The update archive contains too many files.")

            extracted_size = 0
            extracted_paths: set[str] = set()
            for entry in entries:
                if self._is_symlink(entry):
                    raise RuntimeError(f"The update archive contains an unsupported symbolic link: {entry.filename}")
                relative_path = self._safe_archive_path(entry.filename)
                if relative_path is None:
                    continue
                path_key = relative_path.as_posix().casefold()
                if path_key in extracted_paths:
                    raise RuntimeError(f"The update archive contains a duplicate path: {entry.filename}")
                extracted_paths.add(path_key)

                extracted_size += max(0, entry.file_size)
                if extracted_size > self.MAX_EXTRACTED_BYTES:
                    raise RuntimeError("The extracted update is larger than the allowed limit.")

                output_path = destination.joinpath(*relative_path.parts)
                if entry.is_dir():
                    output_path.mkdir(parents=True, exist_ok=True)
                    continue

                output_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry, "r") as source, output_path.open("wb") as target:
                    shutil.copyfileobj(source, target, length=256 * 1024)
                archived_mode = (entry.external_attr >> 16) & 0o777
                if archived_mode:
                    output_path.chmod(archived_mode)

    @staticmethod
    def _safe_archive_path(filename: str) -> PurePosixPath | None:
        normalized = str(filename).replace("\\", "/").strip()
        if not normalized:
            return None
        path = PurePosixPath(normalized)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise RuntimeError(f"Unsafe path in update archive: {filename}")
        if path.parts and ":" in path.parts[0]:
            raise RuntimeError(f"Unsafe path in update archive: {filename}")
        return path

    @staticmethod
    def _is_symlink(entry: zipfile.ZipInfo) -> bool:
        mode = entry.external_attr >> 16
        return stat.S_ISLNK(mode)

    @staticmethod
    def _resolve_content_directory(extraction_directory: Path) -> Path:
        children = [child for child in extraction_directory.iterdir() if child.name != "__MACOSX"]
        files = [child for child in children if child.is_file()]
        directories = [child for child in children if child.is_dir()]
        if not files and len(directories) == 1:
            return directories[0]
        return extraction_directory

    @staticmethod
    def _safe_name(value: str) -> str:
        cleaned = "".join(character if character.isalnum() or character in {"-", ".", "_"} else "-" for character in str(value))
        return cleaned.strip("-._") or "update"

    @staticmethod
    def _current_platform_id() -> str:
        profile = PlatformInfo.current()
        platform_id = f"{profile.os_name}-{profile.architecture}"
        if platform_id not in {"windows-x64", "linux-x64"}:
            raise RuntimeError(f"Automatic launcher updates are not supported on {platform_id}.")
        return platform_id
