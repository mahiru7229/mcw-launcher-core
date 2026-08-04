from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NeoForgeLoaderVersion:
    minecraft_version: str
    neoforge_version: str
    artifact: str = "neoforge"
    coordinate_version: str = ""

    @property
    def resolved_coordinate_version(self) -> str:
        return self.coordinate_version or self.neoforge_version

    @property
    def profile_id(self) -> str:
        return f"neoforge-{self.neoforge_version}"
