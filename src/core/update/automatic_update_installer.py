from __future__ import annotations

from pathlib import Path

from src.core.system.platform_info import PlatformInfo
from src.core.update.linux_update_installer import LinuxUpdateInstaller
from src.core.update.update_errors import AutomaticUpdateUnsupportedError
from src.core.update.windows_update_installer import WindowsUpdateInstaller
from src.models.update.update_info import PreparedUpdate


class AutomaticUpdateInstaller:
    """Route installation to the packaged updater for the current platform."""

    @staticmethod
    def _installer() -> type[WindowsUpdateInstaller] | type[LinuxUpdateInstaller] | None:
        profile = PlatformInfo.current()
        if profile.os_name == "windows" and profile.architecture == "x64":
            return WindowsUpdateInstaller
        if profile.os_name == "linux" and profile.architecture == "x64":
            return LinuxUpdateInstaller
        return None

    @classmethod
    def is_supported(cls) -> bool:
        installer = cls._installer()
        return installer is not None and installer.is_supported()

    @classmethod
    def launch(
        cls,
        prepared: PreparedUpdate,
        install_directory: Path | None = None,
        executable_path: Path | None = None,
        parent_pid: int | None = None,
        persistent_log_path: Path | None = None,
    ) -> Path:
        installer = cls._installer()
        if installer is None:
            profile = PlatformInfo.current()
            raise AutomaticUpdateUnsupportedError(
                f"Automatic launcher updates are not supported on {profile.os_name}-{profile.architecture}."
            )
        return installer.launch(
            prepared,
            install_directory=install_directory,
            executable_path=executable_path,
            parent_pid=parent_pid,
            persistent_log_path=persistent_log_path,
        )

