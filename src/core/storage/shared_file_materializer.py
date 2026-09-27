from __future__ import annotations

from pathlib import Path
from uuid import uuid4
import hashlib
import os
import shutil


from src.core.fs.windows_path import (
    copy_file,
    is_file,
    link_file,
    make_directory,
    open_file,
    replace_path,
    same_file,
    stat_path,
    unlink_file,
)


class SharedFileMaterializer:
    """Reuse immutable files across cache/staging locations when possible."""

    HASH_CHUNK_SIZE = 1024 * 1024

    @classmethod
    def link_or_copy(cls, source: Path, destination: Path) -> bool:
        source_path = Path(source)
        destination_path = Path(destination)
        if not is_file(source_path):
            raise FileNotFoundError(source_path)
        make_directory(destination_path.parent)
        if is_file(destination_path):
            if cls.same_content(source_path, destination_path):
                return cls.same_file(source_path, destination_path)
            unlink_file(destination_path, missing_ok=True)
        try:
            link_file(source_path, destination_path)
            return cls.same_file(source_path, destination_path)
        except OSError:
            copy_file(source_path, destination_path)
            return False

    @classmethod
    def publish_from_staging(cls, source: Path, destination: Path) -> None:
        """Publish a finished installer output into canonical shared storage.

        The staging copy is removed/moved when possible so successful installs
        do not retain a second large physical copy.
        """

        source_path = Path(source)
        destination_path = Path(destination)
        if not is_file(source_path):
            raise FileNotFoundError(source_path)
        source_size = stat_path(source_path).st_size
        make_directory(destination_path.parent)
        if is_file(destination_path) and cls.same_content(source_path, destination_path):
            unlink_file(source_path, missing_ok=True)
            return

        temporary = destination_path.with_name(f".tmp_{uuid4().hex[:8]}.pub")
        unlink_file(temporary, missing_ok=True)
        moved = False
        try:
            try:
                replace_path(source_path, temporary)
                moved = True
            except OSError:
                copy_file(source_path, temporary)
            if not is_file(temporary) or stat_path(temporary).st_size != source_size:
                raise RuntimeError(f"Shared artifact publish was incomplete: {source_path.name}")
            try:
                replace_path(temporary, destination_path)
            except OSError:
                copy_file(temporary, destination_path)
                unlink_file(temporary, missing_ok=True)
            if not moved:
                unlink_file(source_path, missing_ok=True)
        finally:
            unlink_file(temporary, missing_ok=True)

    @classmethod
    def same_content(cls, first: Path, second: Path) -> bool:
        try:
            if stat_path(first).st_size != stat_path(second).st_size:
                return False
        except OSError:
            return False
        if cls.same_file(first, second):
            return True
        return cls._sha256(first) == cls._sha256(second)

    @staticmethod
    def same_file(first: Path, second: Path) -> bool:
        return same_file(first, second)

    @classmethod
    def _sha256(cls, path: Path) -> str:
        digest = hashlib.sha256()
        with open_file(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(cls.HASH_CHUNK_SIZE), b""):
                digest.update(chunk)
        return digest.hexdigest()

