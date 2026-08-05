from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.core.java.java_major_policy import JavaMajorPolicy
from src.core.java.java_manager import JavaManager
from src.core.java.java_provisioner import JavaProvisioner
from src.core.java.java_selector import JavaSelector
from src.core.java.managed_java_repository import ManagedJavaRepository
from src.core.progress.progress_reporter import ProgressReporter
from src.models.progress.progress_stage import ProgressStage


class JavaRecoveryError(RuntimeError):
    """Raised when both the selected Java and automatic recovery fail."""


@dataclass(frozen=True, slots=True)
class JavaResolution:
    path: Path
    automatic: bool
    recovered: bool = False
    recovery_reason: str = ""
    rejected_path: Path | None = None


class JavaResolver:
    @staticmethod
    def resolve(required_major: int, reporter: ProgressReporter | None = None, preferred_path: str | Path | None = None) -> Path:
        managed_major = JavaMajorPolicy.resolve(required_major)
        preferred = str(preferred_path or "").strip()
        if preferred:
            return JavaResolver._validate_preferred(Path(preferred), required_major, managed_major)

        try:
            return JavaSelector.select_java(managed_major)
        except RuntimeError:
            return JavaProvisioner.ensure(managed_major, reporter)

    @staticmethod
    def resolve_with_recovery(required_major: int, reporter: ProgressReporter | None = None, preferred_path: str | Path | None = None) -> JavaResolution:
        preferred = str(preferred_path or "").strip()
        if not preferred:
            return JavaResolution(JavaResolver.resolve(required_major, reporter), automatic=True)

        rejected = JavaManager.normalize_executable(Path(preferred))
        try:
            return JavaResolution(JavaResolver.resolve(required_major, reporter, rejected), automatic=False)
        except RuntimeError as preferred_error:
            if reporter is not None:
                reporter.status(ProgressStage.SELECTING_JAVA, "java.recovery.preferred_invalid")
            try:
                fallback = JavaResolver.resolve_alternative(required_major, {rejected}, reporter)
            except Exception as recovery_error:
                raise JavaRecoveryError(
                    "The configured Java runtime could not be used and automatic Java recovery also failed. "
                    f"Configured Java error: {preferred_error}. Recovery error: {recovery_error}"
                ) from recovery_error
            return JavaResolution(
                fallback,
                automatic=True,
                recovered=True,
                recovery_reason=str(preferred_error),
                rejected_path=rejected,
            )

    @staticmethod
    def resolve_alternative(required_major: int, excluded_paths: set[Path] | tuple[Path, ...] | list[Path], reporter: ProgressReporter | None = None) -> Path:
        managed_major = JavaMajorPolicy.resolve(required_major)
        excluded = {JavaManager.normalize_executable(Path(path)) for path in excluded_paths}
        try:
            candidate = JavaSelector.select_java_excluding(managed_major, excluded)
            return JavaResolver._validate_preferred(candidate, required_major, managed_major)
        except RuntimeError as selection_error:
            if reporter is not None:
                reporter.status(ProgressStage.INSTALLING_JAVA, "java.recovery.installing_managed")

            managed_path = ManagedJavaRepository.executable(managed_major)
            force = JavaResolver._path_key(managed_path) in {JavaResolver._path_key(path) for path in excluded}
            try:
                candidate = JavaProvisioner.install_managed(managed_major, reporter, force=force)
                return JavaResolver._validate_preferred(candidate, required_major, managed_major)
            except Exception as provision_error:
                raise JavaRecoveryError(
                    f"No compatible alternative Java {managed_major} runtime could be selected or installed. "
                    f"Selection error: {selection_error}. Installation error: {provision_error}"
                ) from provision_error

    @staticmethod
    def _validate_preferred(path: Path, required_major: int, managed_major: int) -> Path:
        executable = JavaManager.normalize_executable(path)
        if not executable.is_file():
            raise RuntimeError(f"Java path does not exist: {executable}")

        actual_major = JavaManager.get_major_version(executable)
        if actual_major is None:
            raise RuntimeError(f"Unable to determine the Java version at: {executable}")

        accepted = JavaMajorPolicy.accepted_majors(required_major)
        if actual_major not in accepted:
            expected = " or ".join(f"Java {major}" for major in accepted)
            raise RuntimeError(f"Java {actual_major} is incompatible with this Minecraft runtime. Required: {expected}.")
        return executable

    @staticmethod
    def _path_key(path: Path) -> str:
        try:
            return str(Path(path).resolve(strict=False)).casefold()
        except OSError:
            return str(Path(path)).casefold()
