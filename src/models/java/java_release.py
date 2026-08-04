from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class JavaRelease:
    major: int
    url: str
    sha256: str
    size: int
    filename: str
    release_name: str
