from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.core.java.java_major_policy import JavaMajorPolicy
from src.core.java.java_manager import JavaManager
from src.core.java.java_provisioner import JavaProvisioner
from src.core.java.java_recovery_diagnostics import JavaRecoveryDiagnostics
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
            selected = JavaResolver._validate_preferred(Path(preferred), required_major, managed_major)
            JavaRecoveryDiagnostics.record("preferred_selected", required_major=managed_major, java_path=selected)
            return selected

        # Java 8 is the legacy runtime most likely to be supplied by a decade-old
        # PATH/JAVA_HOME installation. Automatic MCW operations therefore use a
        # managed Temurin 8 runtime. Explicit user-selected Java is still honored.
        if managed_major == 8:
            managed = ManagedJavaRepository.executable(managed_major)
            if managed.is_file():
                JavaRecoveryDiagnostics.record("managed_selected", required_major=managed_major, java_path=managed)
                return managed
            if reporter is not None:
                reporter.status(ProgressStage.INSTALLING_JAVA, "java.recovery.installing_managed")
            JavaRecoveryDiagnostics.record("managed_provision_requested", required_major=managed_major, reason="automatic_java8_policy")
            try:
                installed = JavaProvisioner.install_managed(managed_major, reporter)
            except Exception as provision_error:
                JavaRecoveryDiagnostics.record("managed_provision_failed", required_major=managed_major, error=str(provision_error))
                try:
                    fallback = JavaSelector.select_automatic_java(managed_major)
                except Exception as fallback_error:
                    raise JavaRecoveryError(
                        f"MCW could not provision managed Java {managed_major}, and no suitable modern external Java {managed_major} runtime is available. "
                        f"Managed installation error: {provision_error}. Fallback error: {fallback_error}"
                    ) from provision_error
                JavaRecoveryDiagnostics.record("automatic_external_fallback", required_major=managed_major, java_path=fallback, reason="managed_provision_failed")
                return fallback
            JavaRecoveryDiagnostics.record("managed_provisioned", required_major=managed_major, java_path=installed)
            return installed

        try:
            selected = JavaSelector.select_java(managed_major)
            JavaRecoveryDiagnostics.record("automatic_selected", required_major=managed_major, java_path=selected)
            return selected
        except RuntimeError as selection_error:
            JavaRecoveryDiagnostics.record("automatic_selection_failed", required_major=managed_major, error=str(selection_error))
            installed = JavaProvisioner.install_managed(managed_major, reporter)
            JavaRecoveryDiagnostics.record("managed_provisioned", required_major=managed_major, java_path=installed)
            return installed

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
            JavaRecoveryDiagnostics.record(
                "preferred_rejected",
                required_major=JavaMajorPolicy.resolve(required_major),
                java_path=rejected,
                error=str(preferred_error),
            )
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
        excluded_keys = {JavaResolver._path_key(path) for path in excluded}
        managed_path = ManagedJavaRepository.executable(managed_major)
        provision_error: Exception | None = None

        # Recovery prefers the launcher-owned runtime because its vendor/version and
        # archive checksum are known. If the failed runtime was already the managed
        # one, fall through to another external runtime instead of reinstall looping.
        if JavaResolver._path_key(managed_path) not in excluded_keys:
            try:
                if managed_path.is_file():
                    candidate = JavaResolver._validate_preferred(managed_path, required_major, managed_major)
                    JavaRecoveryDiagnostics.record("recovery_managed_selected", required_major=managed_major, java_path=candidate)
                    return candidate
                if reporter is not None:
                    reporter.status(ProgressStage.INSTALLING_JAVA, "java.recovery.installing_managed")
                JavaRecoveryDiagnostics.record("managed_provision_requested", required_major=managed_major, reason="automatic_recovery")
                candidate = JavaProvisioner.install_managed(managed_major, reporter)
                candidate = JavaResolver._validate_preferred(candidate, required_major, managed_major)
                JavaRecoveryDiagnostics.record("managed_provisioned", required_major=managed_major, java_path=candidate)
                return candidate
            except Exception as error:
                provision_error = error
                JavaRecoveryDiagnostics.record("managed_provision_failed", required_major=managed_major, error=str(error))

        try:
            candidate = JavaSelector.select_automatic_java(managed_major, excluded)
            candidate = JavaResolver._validate_preferred(candidate, required_major, managed_major)
            JavaRecoveryDiagnostics.record("recovery_external_selected", required_major=managed_major, java_path=candidate)
            return candidate
        except RuntimeError as selection_error:
            detail = f"Selection error: {selection_error}."
            if provision_error is not None:
                detail += f" Managed installation error: {provision_error}."
            raise JavaRecoveryError(
                f"No compatible alternative Java {managed_major} runtime could be selected or installed. {detail}"
            ) from (provision_error or selection_error)

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
