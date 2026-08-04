from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FabricComponent:
    uid: str
    version: str
    maven: str = ""
