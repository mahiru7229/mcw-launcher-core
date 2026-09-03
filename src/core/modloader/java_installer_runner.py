from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import signal
import subprocess

from src.core.java.java_resolver import JavaRecoveryError, JavaResolver
from src.core.java.java_recovery_diagnostics import JavaRecoveryDiagnostics
from src.core.java.java_runtime import JavaRuntime
from src.core.progress.progress_reporter import ProgressReporter
from src.core.system.platform_info import PlatformInfo
from src.models.progress.progress_stage import ProgressStage


@dataclass(frozen=True, slots=True)
class ModLoaderInstallerResult:
    returncode: int
    output: str
    java_path: Path
    attempts: int


class ModLoaderJavaRunner:
    """Run a Java-based mod-loader installer with bounded network and Java recovery."""

    TRANSIENT_NETWORK_MARKERS = (
        "unknownhostexception",
        "connectexception",
        "sockettimeoutexception",
        "connection reset",
        "connection timed out",
        "read timed out",
        "connection refused",
        "temporary failure in name resolution",
        "429 too many requests",
        "502 bad gateway",
        "503 service unavailable",
        "504 gateway timeout",
    )

    @staticmethod
    def run(
        required_major: int,
        arguments: list[str],
        cwd: Path,
        reporter: ProgressReporter | None = None,
        preferred_java_path: str | Path | None = None,
        timeout: float = 15 * 60,
    ) -> ModLoaderInstallerResult:
        resolution = JavaResolver.resolve_with_recovery(required_major, reporter, preferred_java_path)
        selected = resolution.path
        attempts: list[tuple[Path, subprocess.CompletedProcess[str] | OSError | subprocess.TimeoutExpired]] = []

        JavaRecoveryDiagnostics.record("modloader_installer_attempt", required_major=required_major, java_path=selected, attempt=1)
        current = ModLoaderJavaRunner._invoke(selected, arguments, cwd, timeout)
        attempts.append((selected, current))
        if ModLoaderJavaRunner._is_transient_network_failure(current):
            if reporter is not None:
                reporter.status(ProgressStage.INSTALLING_MOD_LOADER, "java.mod_loader.retrying")
            JavaRecoveryDiagnostics.record("modloader_installer_attempt", required_major=required_major, java_path=selected, attempt=len(attempts) + 1, reason="network_retry")
            current = ModLoaderJavaRunner._invoke(selected, arguments, cwd, timeout)
            attempts.append((selected, current))

        if ModLoaderJavaRunner._should_retry_java(current):
            if reporter is not None:
                reporter.status(ProgressStage.SELECTING_JAVA, "java.recovery.runtime_failed")
            try:
                selected = JavaResolver.resolve_alternative(required_major, {selected}, reporter)
            except Exception as error:
                details = ModLoaderJavaRunner._attempt_output(attempts)
                raise JavaRecoveryError(
                    "The mod-loader installer could not run with the selected Java runtime, and MCW could not prepare an alternative. "
                    f"Installer details: {details}. Recovery error: {error}"
                ) from error
            if reporter is not None:
                reporter.status(ProgressStage.INSTALLING_MOD_LOADER, "java.mod_loader.retrying")
            JavaRecoveryDiagnostics.record("modloader_installer_attempt", required_major=required_major, java_path=selected, attempt=len(attempts) + 1, reason="java_recovery")
            current = ModLoaderJavaRunner._invoke(selected, arguments, cwd, timeout)
            attempts.append((selected, current))

        final = attempts[-1][1]
        output = ModLoaderJavaRunner._attempt_output(attempts)
        if isinstance(final, OSError):
            raise JavaRecoveryError(
                "The mod-loader installer could not start with the selected Java runtime. "
                f"Installer details: {output}"
            ) from final
        if isinstance(final, subprocess.TimeoutExpired):
            raise JavaRecoveryError(
                f"The mod-loader installer exceeded its {timeout:g}-second timeout. Installer details: {output}"
            ) from final
        JavaRecoveryDiagnostics.record(
            "modloader_installer_completed",
            required_major=required_major,
            java_path=selected,
            attempts=len(attempts),
            returncode=int(final.returncode),
        )
        return ModLoaderInstallerResult(
            returncode=int(final.returncode),
            output=output,
            java_path=selected,
            attempts=len(attempts),
        )

    @staticmethod
    def _invoke(java: Path, arguments: list[str], cwd: Path, timeout: float) -> subprocess.CompletedProcess[str] | OSError | subprocess.TimeoutExpired:
        is_windows = PlatformInfo.is_windows()
        creation_flags = subprocess.CREATE_NO_WINDOW if is_windows else 0
        options: dict[str, object] = {
            "cwd": cwd,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "creationflags": creation_flags,
        }
        if not is_windows:
            options["start_new_session"] = True
        try:
            process = subprocess.Popen(
                [str(java), *arguments],
                **options,
            )
        except OSError as error:
            return error

        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as error:
            ModLoaderJavaRunner._terminate_installer(process)
            stdout, stderr = process.communicate()
            error.stdout = stdout or error.stdout
            error.stderr = stderr or error.stderr
            return error
        return subprocess.CompletedProcess(
            process.args,
            int(process.returncode or 0),
            stdout=stdout,
            stderr=stderr,
        )

    @staticmethod
    def _terminate_installer(process: subprocess.Popen[str]) -> None:
        if not PlatformInfo.is_windows():
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                return
            except (OSError, ProcessLookupError):
                pass
        try:
            process.kill()
        except OSError:
            pass

    @staticmethod
    def _should_retry_java(result: subprocess.CompletedProcess[str] | OSError | subprocess.TimeoutExpired) -> bool:
        if isinstance(result, OSError):
            return True
        if isinstance(result, subprocess.TimeoutExpired) or result.returncode == 0:
            return False
        return JavaRuntime.is_java_runtime_failure(ModLoaderJavaRunner._completed_output(result))

    @staticmethod
    def _is_transient_network_failure(result: subprocess.CompletedProcess[str] | OSError | subprocess.TimeoutExpired) -> bool:
        if not isinstance(result, subprocess.CompletedProcess) or result.returncode == 0:
            return False
        output = ModLoaderJavaRunner._completed_output(result).casefold()
        return any(marker in output for marker in ModLoaderJavaRunner.TRANSIENT_NETWORK_MARKERS)

    @staticmethod
    def _completed_output(result: subprocess.CompletedProcess[str]) -> str:
        stdout = str(result.stdout or "")
        stderr = str(result.stderr or "")
        return stdout + ("\n" if stdout and stderr else "") + stderr

    @staticmethod
    def _attempt_output(attempts: list[tuple[Path, subprocess.CompletedProcess[str] | OSError | subprocess.TimeoutExpired]]) -> str:
        sections: list[str] = []
        for index, (java, result) in enumerate(attempts, start=1):
            header = f"[Java attempt {index}: {java}]"
            if isinstance(result, OSError):
                body = f"{type(result).__name__}: {result}"
            elif isinstance(result, subprocess.TimeoutExpired):
                body = f"TimeoutExpired: installer exceeded {result.timeout:g} seconds."
                captured = ModLoaderJavaRunner._timeout_output(result)
                if captured:
                    body += f"\n{captured}"
            else:
                body = ModLoaderJavaRunner._completed_output(result).strip()
                if not body:
                    body = f"Process exited with code {result.returncode}."
            sections.append(f"{header}\n{body}")
        return "\n\n".join(sections)

    @staticmethod
    def _timeout_output(result: subprocess.TimeoutExpired) -> str:
        values: list[str] = []
        for raw in (result.stdout, result.stderr):
            if raw is None:
                continue
            if isinstance(raw, bytes):
                values.append(raw.decode(errors="replace"))
            else:
                values.append(str(raw))
        return "\n".join(value for value in values if value).strip()
