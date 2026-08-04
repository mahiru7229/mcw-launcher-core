from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import json
import re
import shutil
import zipfile

from src.core.progress.progress_reporter import ProgressReporter
from src.models.progress.progress_stage import ProgressStage


@dataclass(frozen=True, slots=True)
class LegacyForgeInstallResult:
    profile_id: str
    profile: dict
    embedded_library: Path


class LegacyForgeInstaller:
    """Installs pre-1.13 Forge profiles without opening Forge's Swing UI.

    Legacy Forge installers store a complete launcher ``versionInfo`` profile and
    an embedded Forge Universal JAR in the installer archive. They do not expose
    the modern ``--installClient`` command-line option, so MCW imports those
    assets directly into the staging launcher layout.
    """

    PROFILE_NAME = "install_profile.json"
    SHA1_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")

    @staticmethod
    def supports(installer: Path) -> bool:
        try:
            profile = LegacyForgeInstaller.read_profile(installer)
        except (OSError, RuntimeError, zipfile.BadZipFile):
            return False
        return isinstance(profile.get("versionInfo"), dict) and isinstance(profile.get("install"), dict)

    @staticmethod
    def read_profile(installer: Path) -> dict:
        try:
            with zipfile.ZipFile(installer, "r") as archive:
                raw = archive.read(LegacyForgeInstaller.PROFILE_NAME)
        except KeyError as error:
            raise RuntimeError("Forge installer does not contain install_profile.json.") from error
        except (OSError, zipfile.BadZipFile) as error:
            raise RuntimeError("Forge installer archive could not be opened.") from error

        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError("Forge installer contains an invalid install_profile.json.") from error
        if not isinstance(data, dict):
            raise RuntimeError("Forge installer profile must be a JSON object.")
        return data

    @staticmethod
    def install(installer: Path, staging: Path, reporter: ProgressReporter | None = None) -> LegacyForgeInstallResult:
        profile_data = LegacyForgeInstaller.read_profile(installer)
        install_data = profile_data.get("install")
        version_info = profile_data.get("versionInfo")
        if not isinstance(install_data, dict) or not isinstance(version_info, dict):
            raise RuntimeError("This Forge installer is not a supported legacy client installer.")

        profile_id = str(version_info.get("id") or install_data.get("target") or "").strip()
        if not profile_id:
            raise RuntimeError("Legacy Forge installer does not define a target profile ID.")

        relative_library = LegacyForgeInstaller._library_path(install_data, version_info)
        member_name = LegacyForgeInstaller._find_embedded_library(installer, install_data, relative_library)
        target_library = staging / "libraries" / Path(*relative_library.parts)
        target_profile = staging / "versions" / profile_id / f"{profile_id}.json"

        if reporter is not None:
            reporter.files(stage=ProgressStage.INSTALLING_MOD_LOADER, message="Importing legacy Forge installer...", current=0, total=2)

        target_library.parent.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(installer, "r") as archive, archive.open(member_name, "r") as source, target_library.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
        except (OSError, KeyError, zipfile.BadZipFile) as error:
            target_library.unlink(missing_ok=True)
            raise RuntimeError("Could not extract the embedded Forge Universal library.") from error

        if reporter is not None:
            reporter.files(stage=ProgressStage.INSTALLING_MOD_LOADER, message="Importing legacy Forge installer...", current=1, total=2)

        target_profile.parent.mkdir(parents=True, exist_ok=True)
        temp_profile = target_profile.with_suffix(target_profile.suffix + ".tmp")
        temp_profile.write_text(json.dumps(version_info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp_profile.replace(target_profile)

        if reporter is not None:
            reporter.files(stage=ProgressStage.INSTALLING_MOD_LOADER, message="Importing legacy Forge installer...", current=2, total=2)

        return LegacyForgeInstallResult(profile_id=profile_id, profile=version_info, embedded_library=target_library)

    @staticmethod
    def _library_path(install_data: dict, version_info: dict) -> PurePosixPath:
        # ``install.path`` is the Maven destination coordinate. In legacy
        # installers, ``filePath`` usually points to the source JAR inside the
        # installer (for example ``/forge-...-universal.jar``), not to the
        # destination under ``libraries/``.
        coordinate = str(install_data.get("path") or "").strip()
        if not coordinate:
            for library in version_info.get("libraries", []):
                if not isinstance(library, dict):
                    continue
                candidate = str(library.get("name") or "")
                if candidate.startswith("net.minecraftforge:forge:"):
                    coordinate = candidate
                    break
        if coordinate:
            return LegacyForgeInstaller._maven_path(coordinate)

        raw_file_path = str(install_data.get("filePath") or "").replace("\\", "/").lstrip("/")
        if raw_file_path and "/" in raw_file_path:
            return LegacyForgeInstaller._safe_relative_path(raw_file_path)
        raise RuntimeError("Legacy Forge installer does not define its embedded Forge library.")

    @staticmethod
    def _find_embedded_library(installer: Path, install_data: dict, relative_library: PurePosixPath) -> str:
        expected_name = relative_library.name
        candidates = []
        explicit = str(install_data.get("filePath") or "").replace("\\", "/").lstrip("/")
        if explicit:
            candidates.extend((explicit, f"maven/{explicit}"))
        candidates.extend((expected_name, f"/{expected_name}", relative_library.as_posix(), f"maven/{relative_library.as_posix()}"))

        try:
            with zipfile.ZipFile(installer, "r") as archive:
                names = archive.namelist()
        except (OSError, zipfile.BadZipFile) as error:
            raise RuntimeError("Forge installer archive could not be opened.") from error

        normalized_names = {name.replace("\\", "/").lstrip("/"): name for name in names}
        for candidate in candidates:
            normalized = candidate.replace("\\", "/").lstrip("/")
            if normalized in normalized_names:
                return normalized_names[normalized]

        matches = [name for name in names if PurePosixPath(name.replace("\\", "/")).name == expected_name]
        if len(matches) == 1:
            return matches[0]
        universal_matches = [name for name in names if name.replace("\\", "/").lower().endswith("-universal.jar")]
        if len(universal_matches) == 1:
            return universal_matches[0]
        raise RuntimeError(f"Legacy Forge installer does not contain the embedded library '{expected_name}'.")

    @staticmethod
    def _safe_relative_path(value: str) -> PurePosixPath:
        path = PurePosixPath(value)
        if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
            raise RuntimeError(f"Unsafe path in legacy Forge installer: {value}")
        if ":" in path.parts[0]:
            raise RuntimeError(f"Unsafe path in legacy Forge installer: {value}")
        return path

    @staticmethod
    def _maven_path(coordinate: str) -> PurePosixPath:
        raw = str(coordinate).strip()
        extension = "jar"
        if "@" in raw:
            raw, extension = raw.rsplit("@", 1)
            extension = extension.strip() or "jar"
        parts = raw.split(":")
        if len(parts) < 3:
            raise RuntimeError(f"Invalid legacy Forge library coordinate: {coordinate}")
        group, artifact, version = (part.strip() for part in parts[:3])
        classifier = parts[3].strip() if len(parts) > 3 else ""
        if not group or not artifact or not version or any("/" in part or "\\" in part for part in (group, artifact, version, classifier, extension)):
            raise RuntimeError(f"Invalid legacy Forge library coordinate: {coordinate}")
        filename = f"{artifact}-{version}{'-' + classifier if classifier else ''}.{extension}"
        return LegacyForgeInstaller._safe_relative_path("/".join((*group.split("."), artifact, version, filename)))
