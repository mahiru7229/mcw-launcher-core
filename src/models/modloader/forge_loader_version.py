from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ForgeLoaderVersion:
    minecraft_version: str
    forge_version: str

    @property
    def coordinate_version(self) -> str:
        return f"{self.minecraft_version}-{self.forge_version}"

    @property
    def profile_id(self) -> str:
        return f"forge-{self.minecraft_version}-{self.forge_version}"
