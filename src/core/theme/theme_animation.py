from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ThemeAnimationDefinition:
    key: str
    path: str
    frame_width: int
    frame_height: int
    frame_count: int
    columns: int
    frame_duration_ms: int
    loop: bool = True
    render_mode: str = "tile_x"
    filtering: str = "nearest"
    fallback_asset: str | None = None

    @property
    def rows(self) -> int:
        return (self.frame_count + self.columns - 1) // self.columns


@dataclass(frozen=True, slots=True)
class ResolvedThemeAnimation:
    definition: ThemeAnimationDefinition
    path: Path
    theme_id: str

    @property
    def key(self) -> str:
        return self.definition.key
