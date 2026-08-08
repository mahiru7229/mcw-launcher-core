from __future__ import annotations

from pathlib import Path
from uuid import uuid4
import hashlib
import os
import shutil


class SharedFileMaterializer:
    """Reuse immutable files across cache/staging locations when possible."""

    HASH_CHUNK_SIZE = 1024 * 1024

    @classmethod
    def link_or_copy(cls, source: Path, destination: Path) -> bool:
        source_path = Path(source)
        destination_path = Path(destination)
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        if destination_path.exists():
            if cls.same_content(source_path, destination_path):
                return cls.same_file(source_path, destination_path)
            destination_path.unlink()
        try:
            os.link(source_path, destination_path)
            return cls.same_file(source_path, destination_path)
        except OSError:
            shutil.copy2(source_path, destination_path)
            return False

    @classmethod
    def publish_from_staging(cls, source: Path, destination: Path) -> None:
        """Publish a finished installer output into canonical shared storage.

        The staging copy is removed/moved when possible so successful installs
        do not retain a second large physical copy.
        """

        source_path = Path(source)
        destination_path = Path(destination)
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        source_size = source_path.stat().st_size
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        if destination_path.is_file() and cls.same_content(source_path, destination_path):
            source_path.unlink(missing_ok=True)
            return

        temporary = destination_path.with_name(f".{destination_path.name}.{uuid4().hex}.publishing")
        temporary.unlink(missing_ok=True)
        moved = False
        try:
            try:
                os.replace(source_path, temporary)
                moved = True
            except OSError:
                shutil.copy2(source_path, temporary)
            if not temporary.is_file() or temporary.stat().st_size != source_size:
                raise RuntimeError(f"Shared artifact publish was incomplete: {source_path.name}")
            os.replace(temporary, destination_path)
            if not moved:
                source_path.unlink(missing_ok=True)
        finally:
            temporary.unlink(missing_ok=True)

    @classmethod
    def same_content(cls, first: Path, second: Path) -> bool:
        try:
            if first.stat().st_size != second.stat().st_size:
                return False
        except OSError:
            return False
        if cls.same_file(first, second):
            return True
        return cls._sha256(first) == cls._sha256(second)

    @staticmethod
    def same_file(first: Path, second: Path) -> bool:
        try:
            return os.path.samefile(first, second)
        except (FileNotFoundError, OSError):
            return False

    @classmethod
    def _sha256(cls, path: Path) -> str:
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(cls.HASH_CHUNK_SIZE), b""):
                digest.update(chunk)
        return digest.hexdigest()
