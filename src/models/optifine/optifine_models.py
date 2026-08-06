from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
import re


class OptiFineCompatibilityState(StrEnum):
    COMPATIBLE = "compatible"
    WARNING = "warning"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


class OptiFineInstallMode(StrEnum):
    AUTO = "auto"
    STANDALONE = "standalone"
    FORGE_MOD = "forge_mod"


@dataclass(frozen=True, slots=True)
class OptiFineVersion:
    minecraft_version: str
    edition: str
    build: str
    filename: str
    preview: bool = False
    forge_version: str = ""
    release_date: str = ""
    download_page_url: str = "https://optifine.net/downloads"
    mirror_url: str = ""
    changelog_url: str = ""

    @property
    def version_id(self) -> str:
        return f"{self.minecraft_version}_{self.edition}_{self.build}".strip("_")

    @property
    def display_name(self) -> str:
        label = f"{self.edition} {self.build}".strip()
        return f"{label} (preview)" if self.preview else label

    @property
    def forge_supported(self) -> bool:
        return bool(self.forge_version and self.forge_version.casefold() != "n/a")

    @property
    def forge_unavailable(self) -> bool:
        return self.forge_version.casefold() == "n/a"

    @classmethod
    def from_filename(cls, filename: str) -> "OptiFineVersion":
        name = Path(str(filename or "")).name
        match = re.fullmatch(
            r"(?P<preview>preview_)?OptiFine_(?P<minecraft>[0-9]+(?:\.[0-9]+){1,3})_(?P<edition>[A-Za-z0-9]+_[A-Za-z0-9]+)_(?P<build>.+?)(?: \([0-9]+\))?\.jar",
            name,
            re.IGNORECASE,
        )
        if match is None:
            raise ValueError("The selected file name does not contain a supported OptiFine version.")
        build = match.group("build")
        preview = bool(match.group("preview") or re.search(r"(?:^|_)pre[0-9]+(?:_|$)", build, re.IGNORECASE))
        minecraft = match.group("minecraft")
        edition = match.group("edition").upper()
        canonical = f"{'preview_' if preview and match.group('preview') else ''}OptiFine_{minecraft}_{edition}_{build}.jar"
        return cls(
            minecraft_version=minecraft,
            edition=edition,
            build=build,
            filename=canonical,
            preview=preview,
        )


@dataclass(frozen=True, slots=True)
class OptiFineCompatibilityResult:
    state: OptiFineCompatibilityState
    mode: str
    message: str

    @property
    def blocked(self) -> bool:
        return self.state is OptiFineCompatibilityState.BLOCKED


@dataclass(frozen=True, slots=True)
class OptiFineState:
    installed: bool
    minecraft_version: str = ""
    version_id: str = ""
    filename: str = ""
    mode: str = ""
    managed: bool = False
    sha256: str = ""
    size: int = 0
    source_path: str = ""
    installed_path: str = ""
    profile_path: str = ""
    compatibility_state: str = "unknown"
    status: str = "not_installed"


@dataclass(frozen=True, slots=True)
class OptiFineInstallResult:
    instance_name: str
    mode: str
    version_id: str
    installed_path: Path
    repaired: bool = False
