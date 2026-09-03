from pathlib import Path
from urllib.parse import urlparse
from threading import Lock
from uuid import uuid4
import json
import shutil

from src.core.fs.paths import Paths
from src.core.fs.windows_path import move_path, remove_tree
from src.core.java.adoptium_client import AdoptiumClient
from src.core.java.java_archive_downloader import JavaArchiveDownloader
from src.core.java.java_archive_extractor import JavaArchiveExtractor
from src.core.java.java_major_policy import JavaMajorPolicy
from src.core.java.java_manager import JavaManager
from src.core.java.java_recovery_diagnostics import JavaRecoveryDiagnostics
from src.core.java.managed_java_repository import ManagedJavaRepository
from src.core.progress.progress_reporter import ProgressReporter
from src.core.system.platform_info import PlatformInfo
from src.models.java.java_release import JavaRelease
from src.models.progress.progress_stage import ProgressStage


class JavaProvisioner:
    _locks: dict[int, Lock] = {}
    _locks_guard = Lock()

    @classmethod
    def ensure(cls, required_major: int | None, reporter: ProgressReporter | None = None) -> Path:
        managed_major = JavaMajorPolicy.resolve(required_major)
        with cls._get_lock(managed_major):
            installed = cls._find_installed(managed_major)
            if installed is not None:
                return installed
            return cls._download_and_install(managed_major, reporter)

    @classmethod
    def install_managed(cls, required_major: int | None, reporter: ProgressReporter | None = None, force: bool = False) -> Path:
        managed_major = AdoptiumClient.normalize_feature_major(required_major)
        with cls._get_lock(managed_major):
            managed = cls._find_managed(managed_major)
            if managed is not None and not force:
                return managed
            return cls._download_and_install(managed_major, reporter)

    @classmethod
    def _download_and_install(cls, managed_major: int, reporter: ProgressReporter | None) -> Path:
        if not PlatformInfo.supports_managed_java():
            profile = PlatformInfo.current()
            raise RuntimeError(
                f"Managed Java is not available for {profile.os_name} {profile.architecture}."
            )
        if reporter is not None:
            reporter.status(stage=ProgressStage.SELECTING_JAVA, message="java.install.preparing")

        JavaRecoveryDiagnostics.record("metadata_request", required_major=managed_major, provider="Adoptium")
        try:
            release = AdoptiumClient.get_latest_jdk(managed_major)
        except Exception as error:
            JavaRecoveryDiagnostics.record("metadata_failed", required_major=managed_major, error=str(error))
            raise RuntimeError(f"Could not resolve the managed Java {managed_major} download metadata: {error}") from error

        archive_path = ManagedJavaRepository.archive_path(managed_major, release.filename)
        JavaRecoveryDiagnostics.record(
            "download_started",
            required_major=managed_major,
            host=urlparse(release.url).hostname or "",
            expected_size=int(release.size or 0),
            release_name=release.release_name,
        )
        try:
            try:
                JavaArchiveDownloader.download(release, archive_path, reporter)
            except Exception as error:
                JavaRecoveryDiagnostics.record("download_failed", required_major=managed_major, error=str(error))
                raise RuntimeError(f"Managed Java {managed_major} download or SHA-256 verification failed: {error}") from error
            JavaRecoveryDiagnostics.record("download_verified", required_major=managed_major, expected_size=int(release.size or 0), checksum="sha256")
            if reporter is not None:
                reporter.status(stage=ProgressStage.INSTALLING_JAVA, message="java.install.extracting")
            try:
                installed = cls._install_release(release, archive_path)
            except Exception as error:
                JavaRecoveryDiagnostics.record("extract_failed", required_major=managed_major, error=str(error))
                raise RuntimeError(f"Managed Java {managed_major} archive extraction or installation failed: {error}") from error
            JavaRecoveryDiagnostics.record("install_completed", required_major=managed_major, java_path=installed, release_name=release.release_name)
            return installed
        finally:
            archive_path.unlink(missing_ok=True)

    @classmethod
    def _get_lock(cls, major: int) -> Lock:
        with cls._locks_guard:
            return cls._locks.setdefault(major, Lock())

    @staticmethod
    def _find_managed(major: int) -> Path | None:
        managed_executable = ManagedJavaRepository.executable(major)
        return managed_executable if managed_executable.is_file() else None

    @staticmethod
    def _find_installed(major: int) -> Path | None:
        managed_executable = JavaProvisioner._find_managed(major)
        if managed_executable is not None:
            return managed_executable

        exact_matches = [java for java in JavaManager.find_installation() if java.version == major]
        if exact_matches:
            from src.core.java.java_selector import JavaSelector
            return JavaSelector._sort_candidates(exact_matches)[0].executable
        return None

    @staticmethod
    def _install_release(release: JavaRelease, archive_path: Path) -> Path:
        runtime_root = ManagedJavaRepository.root()
        target_dir = ManagedJavaRepository.runtime_dir(release.major)
        staging_dir = Paths.create_short_workspace("jvm")
        backup_dir = runtime_root / f".java-{release.major}.backup-{uuid4().hex}"
        old_runtime_moved = False
        new_runtime_installed = False

        try:
            extracted_java_home = JavaArchiveExtractor.extract(archive_path, staging_dir / "extract")
            if target_dir.exists():
                target_dir.replace(backup_dir)
                old_runtime_moved = True

            move_path(extracted_java_home, target_dir)
            new_runtime_installed = True
            JavaProvisioner._write_marker(target_dir, release)
            executable = target_dir / "bin" / PlatformInfo.current().java_executable
            if not executable.is_file():
                raise RuntimeError(
                    f"Java {release.major} installation finished without {executable.name}."
                )

            if backup_dir.exists():
                remove_tree(backup_dir, ignore_errors=True)
            return executable
        except Exception:
            if new_runtime_installed and target_dir.exists():
                remove_tree(target_dir, ignore_errors=True)
            if old_runtime_moved and backup_dir.exists():
                backup_dir.replace(target_dir)
            raise
        finally:
            Paths.cleanup_short_workspace(staging_dir)
            if backup_dir.exists() and target_dir.exists():
                remove_tree(backup_dir, ignore_errors=True)

    @staticmethod
    def _write_marker(target_dir: Path, release: JavaRelease) -> None:
        marker = {"major": release.major, "release_name": release.release_name, "sha256": release.sha256, "source": "Eclipse Temurin / Adoptium"}
        (target_dir / ".mcw-runtime.json").write_text(json.dumps(marker, indent=4), encoding="utf-8")
