from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FabricLoaderVersion:
    version: str
    stable: bool
    intermediary_version: str = ""
    loader_maven: str = ""
    intermediary_maven: str = ""
