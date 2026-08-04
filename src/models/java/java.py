from dataclasses import dataclass
from src.models.java.java_source import JavaSource
from pathlib import Path


@dataclass(slots=True)
class JavaInstallation:
    version: int
    executable: Path
    source: JavaSource