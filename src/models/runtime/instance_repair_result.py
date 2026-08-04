from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class InstanceRepairResult:
    instance_name: str
    minecraft_version: str
    mod_loader: str
    java_path: Path
    client_path: Path
    libraries_checked: int
    assets_root: Path
    natives_rebuilt: bool
    completed_at: str

    def to_dict(self) -> dict:
        data = asdict(self)
        data["java_path"] = str(self.java_path)
        data["client_path"] = str(self.client_path)
        data["assets_root"] = str(self.assets_root)
        return data
