from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess

from src.core.java.java_resolver import JavaRecoveryError, JavaResolver
from src.core.java.java_runtime import JavaRuntime
from src.core.progress.progress_reporter import ProgressReporter
from src.models.progress.progress_stage import ProgressStage


@dataclass(frozen=True, slots=True)
class ModLoaderInstallerResult:
    returncode: int
    output: str
    java_path: Path
    attempts: int


class ModLoaderJavaRunner:
    """Run a Java-based mod-loader installer with one bounded Java recovery."""

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
        attempts: list[tuple[Path, subprocess.CompletedProcess[str] | OSError]] = []

        first = ModLoaderJavaRunner._invoke(selected, arguments, cwd, timeout)
        attempts.append((selected, first))
        if ModLoaderJavaRunner._should_retry(first):
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
            second = ModLoaderJavaRunner._invoke(selected, arguments, cwd, timeout)
            attempts.append((selected, second))

        final = attempts[-1][1]
        output = ModLoaderJavaRunner._attempt_output(attempts)
        if isinstance(final, OSError):
            raise JavaRecoveryError(
                "The mod-loader installer could not start with the selected Java runtime. "
                f"Installer details: {output}"
            ) from final
        return ModLoaderInstallerResult(
            returncode=int(final.returncode),
            output=output,
            java_path=selected,
            attempts=len(attempts),
        )

    @staticmethod
    def _invoke(java: Path, arguments: list[str], cwd: Path, timeout: float) -> subprocess.CompletedProcess[str] | OSError:
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            return subprocess.run(
                [str(java), *arguments],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=creation_flags,
            )
        except OSError as error:
            return error

    @staticmethod
    def _should_retry(result: subprocess.CompletedProcess[str] | OSError) -> bool:
        if isinstance(result, OSError):
            return True
        if result.returncode == 0:
            return False
        return JavaRuntime.is_java_runtime_failure(ModLoaderJavaRunner._completed_output(result))

    @staticmethod
    def _completed_output(result: subprocess.CompletedProcess[str]) -> str:
        stdout = str(result.stdout or "")
        stderr = str(result.stderr or "")
        return stdout + ("\n" if stdout and stderr else "") + stderr

    @staticmethod
    def _attempt_output(attempts: list[tuple[Path, subprocess.CompletedProcess[str] | OSError]]) -> str:
        sections: list[str] = []
        for index, (java, result) in enumerate(attempts, start=1):
            header = f"[Java attempt {index}: {java}]"
            if isinstance(result, OSError):
                body = f"{type(result).__name__}: {result}"
            else:
                body = ModLoaderJavaRunner._completed_output(result).strip()
                if not body:
                    body = f"Process exited with code {result.returncode}."
            sections.append(f"{header}\n{body}")
        return "\n\n".join(sections)
