from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class JavaRuntimeSummary:
    major: int
    executable: Path
    source: str


@dataclass(frozen=True, slots=True)
class FirstRunRecommendation:
    total_memory_mb: int
    available_memory_mb: int
    recommended_min_memory_mb: int
    recommended_max_memory_mb: int
    java_installations: tuple[JavaRuntimeSummary, ...]
    recommended_java_path: str = ""

    @property
    def java_majors(self) -> tuple[int, ...]:
        return tuple(sorted({item.major for item in self.java_installations}))
