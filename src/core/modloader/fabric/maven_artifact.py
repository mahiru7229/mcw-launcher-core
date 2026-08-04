from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass(frozen=True, slots=True)
class MavenArtifact:
    coordinate: str
    repository_url: str
    path: Path
    url: str

    @staticmethod
    def from_coordinate(coordinate: str, repository_url: str) -> "MavenArtifact":
        coordinate = coordinate.strip()
        repository_url = repository_url.rstrip("/") + "/"

        if not coordinate:
            raise ValueError("Maven coordinate is empty.")

        extension = "jar"
        base_coordinate = coordinate

        if "@" in coordinate:
            base_coordinate, extension = coordinate.rsplit("@", 1)
            extension = extension.strip() or "jar"

        parts = base_coordinate.split(":")
        if len(parts) not in (3, 4):
            raise ValueError(f"Unsupported Maven coordinate: {coordinate}")

        group, artifact, version = parts[:3]
        classifier = parts[3] if len(parts) == 4 else ""

        if not all((group, artifact, version)):
            raise ValueError(f"Invalid Maven coordinate: {coordinate}")

        file_name = f"{artifact}-{version}"
        if classifier:
            file_name += f"-{classifier}"
        file_name += f".{extension}"

        relative_path = PurePosixPath(*group.split("."), artifact, version, file_name)
        return MavenArtifact(coordinate=coordinate, repository_url=repository_url, path=Path(*relative_path.parts), url=repository_url + relative_path.as_posix())
