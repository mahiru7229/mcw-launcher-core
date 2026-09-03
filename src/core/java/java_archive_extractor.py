from __future__ import annotations

from pathlib import Path, PurePosixPath
import os
import stat
import tarfile
from zipfile import ZipFile, ZipInfo, is_zipfile

from src.core.fs.windows_path import make_directory, open_file
from src.core.system.platform_info import PlatformInfo


class JavaArchiveExtractor:
    @staticmethod
    def extract(archive_path: Path, destination: Path) -> Path:
        archive_path = Path(archive_path)
        destination.mkdir(parents=True, exist_ok=False)
        if is_zipfile(archive_path):
            JavaArchiveExtractor._extract_zip(archive_path, destination)
        elif tarfile.is_tarfile(archive_path):
            JavaArchiveExtractor._extract_tar(archive_path, destination)
        else:
            raise RuntimeError(f"Unsupported Java archive format: {archive_path.name}")

        executable = JavaArchiveExtractor._find_java_executable(destination)
        if executable is None:
            expected = PlatformInfo.current().java_executable
            raise RuntimeError(f"The downloaded Java archive does not contain bin/{expected}.")
        if os.name != "nt":
            executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
        return executable.parent.parent

    @staticmethod
    def _extract_zip(archive_path: Path, destination: Path) -> None:
        with ZipFile(archive_path) as archive:
            for member in archive.infolist():
                JavaArchiveExtractor._extract_zip_member(archive, member, destination)

    @staticmethod
    def _extract_zip_member(archive: ZipFile, member: ZipInfo, destination: Path) -> None:
        member_path = JavaArchiveExtractor._safe_member_path(member.filename)
        if member_path is None:
            return
        mode = (member.external_attr >> 16) & 0xFFFF
        if stat.S_ISLNK(mode):
            raise RuntimeError(f"Java ZIP contains a symbolic link: {member.filename}")
        target = destination.joinpath(*member_path.parts)
        if member.is_dir():
            make_directory(target)
            return
        make_directory(target.parent)
        with archive.open(member) as source, open_file(target, "wb") as output:
            while chunk := source.read(1024 * 1024):
                output.write(chunk)
        permissions = stat.S_IMODE(mode)
        if permissions and os.name != "nt":
            target.chmod(permissions)

    @staticmethod
    def _extract_tar(archive_path: Path, destination: Path) -> None:
        try:
            with tarfile.open(archive_path, mode="r:*") as archive:
                # Python's data filter rejects absolute paths, traversal and
                # link targets escaping the destination while retaining safe
                # JDK symlinks and executable permissions on Linux.
                archive.extractall(destination, filter="data")
        except (tarfile.TarError, OSError) as error:
            raise RuntimeError(f"Could not safely extract Java archive {archive_path.name}.") from error

    @staticmethod
    def _safe_member_path(value: str) -> PurePosixPath | None:
        normalized = str(value or "").replace("\\", "/").strip()
        if not normalized:
            return None
        path = PurePosixPath(normalized)
        if (
            path.is_absolute()
            or any(part in {"", ".", ".."} for part in path.parts)
            or (path.parts and ":" in path.parts[0])
        ):
            raise RuntimeError(f"Unsafe path in Java archive: {value}")
        return path

    @staticmethod
    def _find_java_executable(destination: Path) -> Path | None:
        preferred = PlatformInfo.current().java_executable
        names = (preferred, "java", "javaw.exe")
        seen: set[str] = set()
        for name in names:
            if name in seen:
                continue
            seen.add(name)
            candidates = [
                path
                for path in destination.rglob(name)
                if path.is_file() and path.parent.name.casefold() == "bin"
            ]
            if candidates:
                return min(candidates, key=lambda path: len(path.parts))
        return None
