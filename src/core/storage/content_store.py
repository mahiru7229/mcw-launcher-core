from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4
import hashlib
import os
import shutil

from src.core.fs.paths import Paths


@dataclass(frozen=True, slots=True)
class MaterializationResult:
    path: Path
    canonical_path: Path
    sha256: str
    size_bytes: int
    hardlinked: bool


class ContentStore:
    """Content-addressed store for immutable downloaded provider artifacts.

    Provider API/metadata caches intentionally do not use this service.  This
    store only owns binary artifacts such as mods, resource packs, shader packs,
    and provider packages that may be safely reused by hash.
    """

    HASH_CHUNK_SIZE = 1024 * 1024

    @staticmethod
    def sha256(path: Path) -> str:
        source = Path(path)
        digest = hashlib.sha256()
        with source.open("rb") as handle:
            for chunk in iter(lambda: handle.read(ContentStore.HASH_CHUNK_SIZE), b""):
                digest.update(chunk)
        return digest.hexdigest().casefold()

    @classmethod
    def adopt(cls, source: Path) -> MaterializationResult:
        """Publish *source* into the shared store and deduplicate its cache path.

        On filesystems that support hardlinks, the provider cache path and the
        content-store path become two names for the same physical file.  If
        hardlinks are unavailable, the provider cache path is left untouched and
        a verified canonical copy is stored as a compatibility fallback.
        """

        source_path = Path(source)
        if not source_path.is_file():
            raise FileNotFoundError(source_path)

        digest = cls.sha256(source_path)
        target = Paths.content_store_blob(digest)
        target.parent.mkdir(parents=True, exist_ok=True)
        size = source_path.stat().st_size

        if target.is_file():
            cls._verify_blob(target, digest, size)
        else:
            cls._publish_new_blob(source_path, target, digest, size)

        hardlinked = cls._same_file(source_path, target)
        if not hardlinked:
            hardlinked = cls._replace_with_hardlink(source_path, target)

        return MaterializationResult(path=source_path, canonical_path=target, sha256=digest, size_bytes=size, hardlinked=hardlinked)

    @classmethod
    def materialize(cls, source: Path, destination: Path, *, adopt_source: bool = True, prefer_hardlink: bool = True) -> MaterializationResult:
        """Materialize immutable content at *destination* atomically.

        ``adopt_source=True`` publishes the provider download into the shared
        content store first.  This is the normal managed-content path.  Local
        user imports should keep the existing copy semantics and not call this
        helper unless the caller explicitly treats the source as immutable.
        """

        source_path = Path(source)
        if adopt_source:
            published = cls.adopt(source_path)
            canonical = published.canonical_path
            digest = published.sha256
            size = published.size_bytes
        else:
            if not source_path.is_file():
                raise FileNotFoundError(source_path)
            canonical = source_path
            digest = cls.sha256(source_path)
            size = source_path.stat().st_size

        destination_path = Path(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        if destination_path.exists() and cls._same_file(canonical, destination_path):
            return MaterializationResult(path=destination_path, canonical_path=canonical, sha256=digest, size_bytes=size, hardlinked=True)

        temporary = destination_path.with_name(f".{destination_path.name}.{uuid4().hex}.materializing")
        temporary.unlink(missing_ok=True)
        hardlinked = False
        try:
            if prefer_hardlink:
                try:
                    os.link(canonical, temporary)
                    hardlinked = True
                except OSError:
                    hardlinked = False
            if not hardlinked:
                shutil.copy2(canonical, temporary)
            if temporary.stat().st_size != size or cls.sha256(temporary) != digest:
                raise RuntimeError(f"Content materialization verification failed: {destination_path.name}")
            os.replace(temporary, destination_path)
        finally:
            temporary.unlink(missing_ok=True)

        return MaterializationResult(path=destination_path, canonical_path=canonical, sha256=digest, size_bytes=size, hardlinked=hardlinked and cls._same_file(canonical, destination_path))

    @classmethod
    def _publish_new_blob(cls, source: Path, target: Path, digest: str, size: int) -> None:
        try:
            os.link(source, target)
            return
        except FileExistsError:
            cls._verify_blob(target, digest, size)
            return
        except OSError:
            if target.is_file():
                cls._verify_blob(target, digest, size)
                return

        temporary = target.with_name(f".{target.name}.{uuid4().hex}.publishing")
        temporary.unlink(missing_ok=True)
        try:
            shutil.copy2(source, temporary)
            cls._verify_blob(temporary, digest, size)
            if target.is_file():
                cls._verify_blob(target, digest, size)
                return
            try:
                os.replace(temporary, target)
            except OSError:
                if not target.exists():
                    raise
        finally:
            temporary.unlink(missing_ok=True)
        cls._verify_blob(target, digest, size)

    @classmethod
    def _replace_with_hardlink(cls, source: Path, target: Path) -> bool:
        temporary = source.with_name(f".{source.name}.{uuid4().hex}.hardlink")
        temporary.unlink(missing_ok=True)
        try:
            os.link(target, temporary)
            os.replace(temporary, source)
            return cls._same_file(source, target)
        except OSError:
            return False
        finally:
            temporary.unlink(missing_ok=True)

    @classmethod
    def _verify_blob(cls, path: Path, digest: str, size: int) -> None:
        if not path.is_file() or path.stat().st_size != size or cls.sha256(path) != digest:
            raise RuntimeError(f"Shared content store blob failed verification: {path}")

    @staticmethod
    def _same_file(first: Path, second: Path) -> bool:
        try:
            return os.path.samefile(first, second)
        except (FileNotFoundError, OSError):
            return False
