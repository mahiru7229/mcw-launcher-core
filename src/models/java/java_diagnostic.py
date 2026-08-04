from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.models.java.java_source import JavaSource


@dataclass(frozen=True, slots=True)
class JavaDiagnostic:
    major_version: int
    version_string: str
    vendor: str
    architecture: str
    java_home: str
    executable: Path
    source: JavaSource
    valid: bool = True

    @property
    def display_name(self) -> str:
        vendor = self.vendor or "Unknown vendor"
        version = self.version_string or str(self.major_version)
        architecture = self.architecture or "unknown architecture"
        return f"{vendor} {version} — {architecture}"
