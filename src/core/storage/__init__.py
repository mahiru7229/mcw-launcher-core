"""Shared storage and lifecycle services for MCW Launcher."""

from src.core.storage.content_store import ContentStore, MaterializationResult
from src.core.storage.legacy_storage_migration_service import CleanupCandidate, CleanupPlan, CleanupResult, LegacyCleanupProbe, LegacyStorageMigrationService
from src.core.storage.platform_storage_migration import PlatformStorageMigration, PlatformStorageMigrationReport, platform_storage_migration

__all__ = [
    "CleanupCandidate",
    "CleanupPlan",
    "CleanupResult",
    "LegacyCleanupProbe",
    "ContentStore",
    "LegacyStorageMigrationService",
    "MaterializationResult",
    "PlatformStorageMigration",
    "PlatformStorageMigrationReport",
    "platform_storage_migration",
]
