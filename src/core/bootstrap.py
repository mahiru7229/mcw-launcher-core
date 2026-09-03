from __future__ import annotations

from collections.abc import Callable
import os
from typing import Any

from src.core.account.database.account_database import AccountDatabase
from src.core.config.launcher_settings_manager import LauncherSettingsManager
from src.core.fs.paths import Paths
from src.core.network.download_bandwidth_limiter import download_bandwidth_limiter
from src.core.network.download_manager import download_manager
from src.core.network.download_recovery import download_recovery_manager
from src.core.network.network_session import DEFAULT_MAX_CONCURRENT_DOWNLOADS
from src.core.security.account_security_manager import AccountSecurityManager
from src.core.runtime.startup_recovery_manager import startup_recovery_manager
from src.core.storage.platform_storage_migration import platform_storage_migration
from src.core.system.platform_info import PlatformInfo

BootstrapProgressCallback = Callable[[int, str], None]


def _report(callback: BootstrapProgressCallback | None, percent: int, message_key: str) -> None:
    if callback is not None:
        callback(percent, message_key)


def initialize_application(progress_callback: BootstrapProgressCallback | None = None) -> dict[str, Any]:
    """Prepare persistent application resources and report startup progress when requested."""
    _report(progress_callback, 4, "startup.configuring_storage")
    Paths.configure_application_defaults(platform_name=PlatformInfo.current().os_name)

    _report(progress_callback, 6, "startup.migrating_storage")
    legacy_root = str(os.environ.get("MCW_LEGACY_ROOT") or "").strip() or Paths.PROJECT_ROOT
    migration = platform_storage_migration.migrate(legacy_root)
    if migration.errors:
        details = "; ".join(migration.errors[:3])
        raise RuntimeError(f"Could not safely migrate launcher data into the platform storage layout: {details}")

    _report(progress_callback, 8, "startup.preparing_directories")
    Paths.initialize()

    _report(progress_callback, 18, "startup.recovering_instances")
    startup_recovery_manager.reconcile()

    _report(progress_callback, 28, "startup.loading_settings")
    settings_manager = LauncherSettingsManager()
    settings_manager.initialize()
    settings = settings_manager.load()

    _report(progress_callback, 44, "startup.configuring_downloads")
    network_settings = settings.get("network", {})
    download_bandwidth_limiter.configure_mbps(network_settings.get("download_limit_mbps", 0.0))
    configured_concurrency = int(network_settings.get("download_concurrency", 0) or 0)
    download_manager.configure(configured_concurrency or DEFAULT_MAX_CONCURRENT_DOWNLOADS)

    _report(progress_callback, 56, "startup.recovering_downloads")
    download_recovery_manager.reconcile(delete_invalid_parts=True)

    _report(progress_callback, 68, "startup.preparing_accounts")
    AccountDatabase.initialize()

    _report(progress_callback, 82, "startup.protecting_accounts")
    AccountSecurityManager.migrate_if_needed()

    _report(progress_callback, 90, "startup.core_ready")
    return settings
