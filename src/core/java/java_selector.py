from pathlib import Path

from src.core.java.java_manager import JavaManager
from src.models.java.java import JavaInstallation
from src.models.java.java_source import JavaSource


class JavaSelector:
    _SOURCE_PRIORITY = {
        JavaSource.MINECRAFT_RUNTIME: 4,
        JavaSource.PROGRAM_FILES: 3,
        JavaSource.JAVA_HOME: 2,
        JavaSource.REGISTRY: 1,
        JavaSource.PATH: 0,
    }

    @staticmethod
    def select_java(required_major: int, allow_higher: bool = False) -> Path:
        javas = JavaManager.find_installation()

        if not javas:
            raise RuntimeError("No Java found.")

        exact_matches = [java for java in javas if java.version == required_major]
        if exact_matches:
            return exact_matches[0].executable

        if allow_higher:
            higher_versions = [java for java in javas if java.version > required_major]
            if higher_versions:
                return min(higher_versions, key=lambda java: java.version).executable

        raise RuntimeError(f"Java {required_major} was not found.")

    @staticmethod
    def select_java_excluding(required_major: int, excluded_paths: set[Path] | tuple[Path, ...] | list[Path], allow_higher: bool = False) -> Path:
        excluded = {JavaSelector._path_key(path) for path in excluded_paths}
        javas = [java for java in JavaManager.find_installation_candidates() if JavaSelector._path_key(java.executable) not in excluded]
        if not javas:
            raise RuntimeError("No alternative Java runtime was found.")

        exact_matches = JavaSelector._sort_candidates([java for java in javas if java.version == required_major])
        if exact_matches:
            return exact_matches[0].executable

        if allow_higher:
            higher_versions = [java for java in javas if java.version > required_major]
            if higher_versions:
                nearest = min(java.version for java in higher_versions)
                matches = JavaSelector._sort_candidates([java for java in higher_versions if java.version == nearest])
                return matches[0].executable

        raise RuntimeError(f"No alternative Java {required_major} runtime was found.")

    @staticmethod
    def select_latest_java() -> Path:
        javas = JavaManager.find_installation()

        if not javas:
            raise RuntimeError("No Java found.")

        return max(javas, key=lambda java: java.version).executable

    @staticmethod
    def _sort_candidates(candidates: list[JavaInstallation]) -> list[JavaInstallation]:
        return sorted(candidates, key=lambda java: JavaSelector._SOURCE_PRIORITY.get(java.source, -1), reverse=True)

    @staticmethod
    def _path_key(path: Path) -> str:
        try:
            return str(Path(path).resolve(strict=False)).casefold()
        except OSError:
            return str(Path(path)).casefold()
