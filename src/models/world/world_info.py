from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class WorldInfo:
    """Metadata representing a singleplayer Minecraft save."""

    folder_name: str
    display_name: str
    game_mode: str = "survival"
    is_hardcore: bool = False
    last_played: int = 0  # Epoch milliseconds
    version_name: str = ""
    folder_size_bytes: int = 0
    icon_path: str = ""
    folder_path: Path | None = None

    @property
    def name(self) -> str:
        return self.display_name

    @property
    def hardcore(self) -> bool:
        return self.is_hardcore

    @property
    def total_size_bytes(self) -> int:
        return self.folder_size_bytes
