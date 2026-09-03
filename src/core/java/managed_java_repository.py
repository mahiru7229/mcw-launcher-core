from pathlib import Path

from src.core.fs.paths import Paths
from src.core.system.platform_info import PlatformInfo


class ManagedJavaRepository:
    @staticmethod
    def root() -> Path:
        path = Paths.RUNTIMES_ROOT
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def runtime_dir(major: int) -> Path:
        return ManagedJavaRepository.root() / f"java-{major}"

    @staticmethod
    def executable(major: int) -> Path:
        return ManagedJavaRepository.runtime_dir(major) / "bin" / PlatformInfo.current().java_executable

    @staticmethod
    def archive_path(major: int, filename: str | None = None) -> Path:
        downloads_dir = ManagedJavaRepository.root() / "downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)
        suffix = PlatformInfo.current().archive_suffix
        candidate = Path(str(filename or "")).name
        if candidate and candidate.casefold().endswith(suffix.casefold()):
            archive_name = candidate
        else:
            archive_name = f"temurin-java-{major}{suffix}"
        return downloads_dir / archive_name

    @staticmethod
    def is_installed(major: int) -> bool:
        return ManagedJavaRepository.executable(major).is_file()
