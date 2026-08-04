from pathlib import Path, PurePosixPath
from zipfile import ZipFile, ZipInfo


class JavaArchiveExtractor:
    @staticmethod
    def extract(archive_path: Path, destination: Path) -> Path:
        destination.mkdir(parents=True, exist_ok=False)
        with ZipFile(archive_path) as archive:
            for member in archive.infolist():
                JavaArchiveExtractor._extract_member(archive, member, destination)

        javaw_path = JavaArchiveExtractor._find_javaw(destination)
        if javaw_path is None:
            raise RuntimeError("The downloaded Java archive does not contain bin/javaw.exe.")
        return javaw_path.parent.parent

    @staticmethod
    def _extract_member(archive: ZipFile, member: ZipInfo, destination: Path) -> None:
        member_path = PurePosixPath(member.filename)
        if member_path.is_absolute() or ".." in member_path.parts:
            raise RuntimeError(f"Unsafe path in Java archive: {member.filename}")
        if not member_path.parts:
            return

        target = destination.joinpath(*member_path.parts)
        if member.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            return

        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as source, target.open("wb") as output:
            while chunk := source.read(1024 * 1024):
                output.write(chunk)

    @staticmethod
    def _find_javaw(destination: Path) -> Path | None:
        candidates = [path for path in destination.rglob("javaw.exe") if path.parent.name.lower() == "bin"]
        if not candidates:
            return None
        return min(candidates, key=lambda path: len(path.parts))
