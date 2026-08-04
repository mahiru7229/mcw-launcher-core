from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class QuiltLoaderVersion:
    version: str
    stable: bool
    mappings_version: str = ""
    loader_maven: str = ""
    mappings_maven: str = ""
