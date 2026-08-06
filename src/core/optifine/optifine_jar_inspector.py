from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import zipfile

from src.models.optifine.optifine_models import OptiFineVersion


@dataclass(frozen=True, slots=True)
class InspectedOptiFineJar:
    path: Path
    filename: str
    sha256: str
    sha1: str
    size: int
    version: OptiFineVersion


class OptiFineJarInspector:
    MAX_SIZE = 128 * 1024 * 1024
    REQUIRED_ANY = {"optifine/Installer.class", "optifine/Config.class", "net/optifine/Config.class"}

    @classmethod
    def detect_version(cls, path: Path | str) -> OptiFineVersion:
        source = Path(path)
        try:
            return OptiFineVersion.from_filename(source.name)
        except ValueError as error:
            raise RuntimeError("The selected file name does not contain a supported OptiFine version.") from error

    @classmethod
    def inspect(cls, path: Path, expected_minecraft_version: str = "") -> InspectedOptiFineJar:
        source = Path(path).expanduser().resolve(strict=False)
        if not source.is_file():
            raise FileNotFoundError(f"OptiFine JAR was not found: {source}")
        size = source.stat().st_size
        if size <= 0 or size > cls.MAX_SIZE:
            raise RuntimeError("The selected OptiFine file is empty or unexpectedly large.")
        if source.suffix.casefold() != ".jar":
            raise RuntimeError("Select an official OptiFine .jar file.")
        detected = cls.detect_version(source)
        expected = str(expected_minecraft_version or "").strip()
        if expected and detected.minecraft_version != expected:
            raise RuntimeError(
                f"The selected OptiFine JAR targets Minecraft {detected.minecraft_version}, not {expected}."
            )
        try:
            with zipfile.ZipFile(source) as archive:
                names = {name.replace("\\", "/") for name in archive.namelist()}
                if not names.intersection(cls.REQUIRED_ANY):
                    raise RuntimeError("The selected JAR does not contain the expected OptiFine classes.")
                if "META-INF/MANIFEST.MF" not in names:
                    raise RuntimeError("The selected JAR has no Java manifest.")
        except zipfile.BadZipFile as error:
            raise RuntimeError("The selected OptiFine JAR is corrupt or incomplete.") from error
        sha256 = hashlib.sha256()
        sha1 = hashlib.sha1()
        with source.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                sha256.update(chunk)
                sha1.update(chunk)
        return InspectedOptiFineJar(source, detected.filename, sha256.hexdigest(), sha1.hexdigest(), size, detected)
