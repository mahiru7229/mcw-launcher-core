from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class QuiltComponent:
    uid: str
    version: str
    maven: str = ""
