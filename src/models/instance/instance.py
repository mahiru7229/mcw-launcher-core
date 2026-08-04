from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Instance:
    instance_id: str
    name: str
    version_id: str
    instance_dir: Path
    mod_loader: tuple[str, str]
    icon: str = "grass_block"
    last_played: str = ""
    last_exit_code: int | None = None
    last_launch_crashed: bool = False
    last_launch_state: str = "ready"
