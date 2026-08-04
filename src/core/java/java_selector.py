from pathlib import Path

from src.core.java.java_manager import JavaManager


class JavaSelector:
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
    def select_latest_java() -> Path:
        javas = JavaManager.find_installation()

        if not javas:
            raise RuntimeError("No Java found.")

        return max(javas, key=lambda java: java.version).executable
