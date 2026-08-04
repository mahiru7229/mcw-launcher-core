from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ThemeFontDefinition:
    paths: tuple[str, ...]
    family: str | None = None
    point_size: float = 10.5
    weight: int = 400
    italic: bool = False
    letter_spacing: float = 0.0
    fallback_families: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResolvedThemeFont:
    definition: ThemeFontDefinition
    paths: tuple[Path, ...]
    theme_id: str
