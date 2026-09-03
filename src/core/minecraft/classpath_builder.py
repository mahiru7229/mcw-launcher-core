from pathlib import Path
import os

from src.core.minecraft.library_rule_manager import LibraryRuleManager
from src.core.minecraft.metadata_validation import MinecraftMetadataValidation
from src.models.minecraft.version import Version


class ClasspathBuilder:

    @staticmethod
    def build(version: Version, client_path: Path, libraries_dir: Path) -> str:
        classpath: list[str] = []
        for library in version.libraries:
            if not LibraryRuleManager.is_allowed(library) or library.get("clientreq") is False:
                continue
            artifact_path = ClasspathBuilder._artifact_path(library, libraries_dir)
            if artifact_path is None:
                continue
            classpath.append(str(libraries_dir / artifact_path))
        classpath.append(str(client_path))
        return os.pathsep.join(classpath)

    @staticmethod
    def _artifact_path(library: dict, libraries_dir: Path) -> Path | None:
        downloads = library.get("downloads") if isinstance(library.get("downloads"), dict) else {}
        artifact = downloads.get("artifact") if isinstance(downloads.get("artifact"), dict) else {}
        configured = str(artifact.get("path") or "").strip()
        if configured:
            return MinecraftMetadataValidation.relative_path(configured, "library classpath")

        legacy = ClasspathBuilder._legacy_maven_path(str(library.get("name") or ""))
        if legacy is None or not (libraries_dir / legacy).is_file():
            return None
        return legacy

    @staticmethod
    def _legacy_maven_path(coordinate: str) -> Path | None:
        raw = str(coordinate).strip()
        extension = "jar"
        if "@" in raw:
            raw, extension = raw.rsplit("@", 1)
            extension = extension.strip() or "jar"
        parts = [part.strip() for part in raw.split(":")]
        if len(parts) < 3:
            return None
        group, artifact, version = parts[:3]
        classifier = parts[3] if len(parts) > 3 else ""
        values = (group, artifact, version, classifier, extension)
        if not group or not artifact or not version or any("/" in value or "\\" in value for value in values):
            return None
        filename = f"{artifact}-{version}{'-' + classifier if classifier else ''}.{extension}"
        return MinecraftMetadataValidation.relative_path(
            Path(*group.split("."), artifact, version, filename).as_posix(),
            "legacy library classpath",
        )
