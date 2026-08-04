from __future__ import annotations

from dataclasses import dataclass
import re


_VERSION_PATTERN = re.compile(
    r"^v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?:\.(?P<revision>\d+))?"
    r"(?:[\s._-]*(?P<label>alpha|beta|rc|pre)[\s._-]*(?P<number>\d+)?)?$",
    re.IGNORECASE,
)


@dataclass(frozen=True, order=False, slots=True)
class LauncherVersion:
    major: int
    minor: int
    patch: int
    prerelease: str | None = None
    prerelease_number: int = 0
    revision: int = 0

    _PRERELEASE_ORDER = {
        "alpha": 0,
        "pre": 0,
        "beta": 1,
        "rc": 2,
    }

    @classmethod
    def parse(cls, value: str) -> "LauncherVersion":
        normalized = str(value).strip()
        match = _VERSION_PATTERN.fullmatch(normalized)
        if match is None:
            raise ValueError(f"Invalid launcher version: {value!r}")

        label = match.group("label")
        return cls(
            major=int(match.group("major")),
            minor=int(match.group("minor")),
            patch=int(match.group("patch")),
            prerelease=label.lower() if label else None,
            prerelease_number=int(match.group("number") or 0),
            revision=int(match.group("revision") or 0),
        )

    @property
    def is_prerelease(self) -> bool:
        return self.prerelease is not None

    def comparison_key(self) -> tuple[int, int, int, int, int, int]:
        if self.prerelease is None:
            prerelease_rank = 3
        else:
            prerelease_rank = self._PRERELEASE_ORDER.get(self.prerelease, -1)
        return self.major, self.minor, self.patch, self.revision, prerelease_rank, self.prerelease_number

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, LauncherVersion):
            return NotImplemented
        return self.comparison_key() < other.comparison_key()

    def __le__(self, other: object) -> bool:
        if not isinstance(other, LauncherVersion):
            return NotImplemented
        return self.comparison_key() <= other.comparison_key()

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, LauncherVersion):
            return NotImplemented
        return self.comparison_key() > other.comparison_key()

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, LauncherVersion):
            return NotImplemented
        return self.comparison_key() >= other.comparison_key()

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.revision > 0:
            base += f".{self.revision}"
        if self.prerelease is None:
            return base
        suffix = f"-{self.prerelease}"
        if self.prerelease_number > 0:
            suffix += f".{self.prerelease_number}"
        return base + suffix
