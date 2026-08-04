from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ModpackExportOptions:
    mode: str
    portable_mode: str = "smart"
    include_saves: bool = False

    PROVIDER_PROFILE = "provider_profile"
    PORTABLE = "portable"
    SMART = "smart"
    FULL = "full"

    def normalized(self) -> "ModpackExportOptions":
        mode = str(self.mode or "").strip().casefold()
        portable_mode = str(self.portable_mode or "").strip().casefold()
        if mode not in {self.PROVIDER_PROFILE, self.PORTABLE}:
            raise ValueError(f"Unsupported modpack export mode: {self.mode}")
        if portable_mode not in {self.SMART, self.FULL}:
            portable_mode = self.SMART
        return ModpackExportOptions(mode=mode, portable_mode=portable_mode, include_saves=bool(self.include_saves))


@dataclass(frozen=True, slots=True)
class ModpackExportResult:
    output_path: Path
    mode: str
    referenced_files: int = 0
    embedded_files: int = 0
    manual_files: int = 0
    native_package_included: bool = False
