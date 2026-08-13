from __future__ import annotations

from pathlib import Path
import os
import re
import subprocess

from src.core.java.java_manager import JavaManager
from src.core.progress.progress_reporter import ProgressReporter
from src.models.progress.progress_stage import ProgressStage
from src.models.java.java_diagnostic import JavaDiagnostic
from src.models.java.java import JavaInstallation


class JavaDiagnosticsManager:
    PROPERTY_PATTERN = re.compile(r"^\s*([^=]+?)\s*=\s*(.*?)\s*$")

    @staticmethod
    def scan(reporter: ProgressReporter | None = None) -> list[JavaDiagnostic]:
        installations = JavaManager.find_installation(reporter=reporter)
        diagnostics: list[JavaDiagnostic] = []
        total = max(len(installations), 1)

        if not installations and reporter is not None:
            reporter.steps(ProgressStage.SELECTING_JAVA, "java.scan.no_installations", 1, 1)

        for index, java in enumerate(installations, start=1):
            if reporter is not None:
                reporter.steps(ProgressStage.SELECTING_JAVA, "java.scan.inspecting", index - 1, total)
            diagnostics.append(JavaDiagnosticsManager.inspect(java))

        if installations and reporter is not None:
            reporter.steps(ProgressStage.SELECTING_JAVA, "java.scan.completed", total, total)
        return sorted(diagnostics, key=lambda item: (item.major_version, item.vendor.casefold(), str(item.executable).casefold()))

    @staticmethod
    def inspect(java: JavaInstallation) -> JavaDiagnostic:
        properties = JavaDiagnosticsManager._read_properties(java.executable)
        version_string = properties.get("java.version", "")
        vendor = properties.get("java.vendor", "")
        architecture = properties.get("os.arch", "")
        java_home = properties.get("java.home", "")
        return JavaDiagnostic(major_version=java.version, version_string=version_string, vendor=vendor, architecture=architecture, java_home=java_home, executable=Path(java.executable), source=java.source, valid=bool(properties))

    @staticmethod
    def _read_properties(executable: Path) -> dict[str, str]:
        java_path = Path(executable)
        console_path = JavaManager._version_probe_executable(java_path)
        try:
            result = subprocess.run([str(console_path), "-XshowSettings:properties", "-version"], capture_output=True, text=True, timeout=10, creationflags=JavaManager._creation_flags())
        except (subprocess.SubprocessError, FileNotFoundError, PermissionError, OSError):
            return {}
        output = "\n".join(part for part in (result.stdout, result.stderr) if part)
        properties: dict[str, str] = {}
        for line in output.splitlines():
            match = JavaDiagnosticsManager.PROPERTY_PATTERN.match(line)
            if match:
                properties[match.group(1).strip()] = match.group(2).strip()
        return properties

    @staticmethod
    def open_directory(java: JavaDiagnostic) -> Path:
        directory = java.executable.parent.parent if java.executable.parent.name.casefold() == "bin" else java.executable.parent
        if not directory.exists():
            raise RuntimeError(f"Java directory no longer exists: {directory}")
        return directory
