from pathlib import Path

from src.core.fs.paths import Paths


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
        return ManagedJavaRepository.runtime_dir(major) / "bin" / "javaw.exe"

    @staticmethod
    def archive_path(major: int) -> Path:
        downloads_dir = ManagedJavaRepository.root() / "downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)
        return downloads_dir / f"temurin-java-{major}.zip"

    @staticmethod
    def is_installed(major: int) -> bool:
        return ManagedJavaRepository.executable(major).is_file()
