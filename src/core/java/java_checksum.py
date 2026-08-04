import hashlib
from pathlib import Path

from src.core.network.download_pause import download_pause_controller


class JavaChecksum:
    @staticmethod
    def sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            while chunk := file.read(1024 * 1024):
                download_pause_controller.raise_if_requested()
                digest.update(chunk)
        return digest.hexdigest().lower()

    @staticmethod
    def verify_sha256(path: Path, expected_sha256: str) -> bool:
        if not path.is_file():
            return False
        try:
            return JavaChecksum.sha256(path) == expected_sha256.lower()
        except OSError:
            return False
