from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InstalledContentItem:
    item_id: str
    content_type: str
    name: str
    version: str
    provider: str
    project_id: str
    version_id: str
    file_id: str
    file_name: str
    target_path: str
    enabled: bool
    managed_by_modpack: bool
    source_pack_provider: str
    size: int
    sha1: str
    sha512: str
    project_url: str
    status: str
    pinned: bool = False
    ignored_update: bool = False
    toggleable: bool = False
    removable: bool = False


@dataclass(frozen=True, slots=True)
class InstalledContentLibrary:
    instance_name: str
    items: tuple[InstalledContentItem, ...]

    @property
    def total_count(self) -> int:
        return len(self.items)

    @property
    def enabled_count(self) -> int:
        return sum(1 for item in self.items if item.enabled and item.status not in {"missing", "pending"})

    @property
    def pending_count(self) -> int:
        return sum(1 for item in self.items if item.status == "pending")

    @property
    def missing_count(self) -> int:
        return sum(1 for item in self.items if item.status == "missing")

    @property
    def managed_count(self) -> int:
        return sum(1 for item in self.items if item.managed_by_modpack)

    @property
    def total_size(self) -> int:
        return sum(max(0, int(item.size)) for item in self.items)
