from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ReleaseAsset:
    name: str
    download_url: str
    size: int
    sha256: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateInfo:
    current_version: str
    version: str
    tag_name: str
    title: str
    release_notes: str
    release_url: str
    published_at: str
    prerelease: bool
    asset: ReleaseAsset


@dataclass(frozen=True, slots=True)
class PreparedUpdate:
    info: UpdateInfo
    archive_path: Path
    staging_directory: Path
    content_directory: Path
