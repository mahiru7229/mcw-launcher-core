from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from zipfile import BadZipFile, ZipFile
import hashlib
import re

from src.config import MODRINTH_USER_AGENT
from src.core.language.language_manager import tr
from src.core.network.artifact_download_service import ArtifactDownloadError, ArtifactDownloadService
from src.core.progress.progress_reporter import ProgressReporter
from src.models.instance.instance import Instance
from src.models.network.artifact import ArtifactRequest
from src.models.progress.progress_stage import ProgressStage


_MANIFEST_NAME = "META-INF/MANIFEST.MF"
_SHA512_PATTERN = re.compile(r"^[0-9a-f]{128}$", re.IGNORECASE)
_ALLOWED_SOURCE_HOSTS = {"jcenter.bintray.com", "repo1.maven.org", "repo.maven.apache.org"}
_TACKPROFILER_BASE = "https://raw.githubusercontent.com/quat1024/TackProfiler/trunk/src/main/resources/cached-libloader-libs"
_TACKPROFILER_COORDINATES = {
    ("com.eclipsesource.minimal-json", "minimal-json", "0.9.4"),
    ("com.github.javaparser", "javaparser-core", "3.2.4"),
    ("me.nallar.whocalled", "WhoCalled", "1.1"),
    ("org.javassist", "javassist", "3.22.0-CR1"),
    ("org.json", "json", "20090211"),
    ("org.minimallycorrect.javatransformer", "JavaTransformer", "1.8.3"),
}
_MAX_LIBRARY_BYTES = 64 * 1024 * 1024
_MAX_ROUNDS = 8


@dataclass(frozen=True, slots=True)
class LegacyLibLoaderDependency:
    group: str
    name: str
    version: str
    sha512: str
    source_jar: Path
    classifier: str = ""
    url: str = ""
    embedded_file: str = ""
    build_time: int = 0

    @property
    def key(self) -> str:
        return f"{self.group}.{self.name}"

    @property
    def display_name(self) -> str:
        classifier = f"-{self.classifier}" if self.classifier else ""
        return f"{self.group}.{self.name}{classifier}-{self.version}"

    @property
    def mirror_filename(self) -> str:
        classifier = f"-{self.classifier}" if self.classifier else ""
        return f"{self.group}.{self.name}-{self.version}{classifier}.jar"

    @property
    def relative_path(self) -> Path:
        classifier = f"-{self.classifier}" if self.classifier else ""
        filename = f"{self.name}-{self.version}{classifier}.jar"
        group_path = Path(*self.group.split("."))
        if "-" in self.version:
            directory = f"{self.name}-{self.version}-{self.sha512[:16]}"
        else:
            directory = f"{self.name}-{self.version}"
        return group_path / directory / filename


class LegacyLibLoaderManager:
    @staticmethod
    def ensure(instance: Instance, reporter: ProgressReporter | None = None, service: ArtifactDownloadService | None = None) -> tuple[str, ...]:
        loader_name = str((getattr(instance, "mod_loader", ("", "")) or ("", ""))[0]).strip().casefold()
        if loader_name != "forge":
            return ()

        mods_dir = Path(instance.instance_dir) / "mods"
        if not mods_dir.is_dir():
            return ()

        sources = sorted(path for path in mods_dir.iterdir() if path.is_file() and path.suffix.casefold() == ".jar")
        dependencies = {key: dependency for key, dependency in LegacyLibLoaderManager._collect_dependencies(sources).items() if LegacyLibLoaderManager._manageable(dependency)}
        if not dependencies:
            return ()

        if reporter is not None:
            reporter.status(ProgressStage.DOWNLOADING_LIBRARIES, "progress.forge.legacy_libloader_check")

        downloader = service or ArtifactDownloadService()
        libraries_dir = Path(instance.instance_dir) / "libraries"
        downloaded = 0
        processed_sources = {path.resolve(strict=False) for path in sources}

        for _ in range(_MAX_ROUNDS):
            pending = [dependency for dependency in dependencies.values() if not LegacyLibLoaderManager._valid(libraries_dir / dependency.relative_path, dependency.sha512)]
            if not pending:
                break
            new_sources: list[Path] = []
            total = len(pending)
            for index, dependency in enumerate(sorted(pending, key=lambda item: item.display_name.casefold()), start=1):
                if reporter is not None:
                    reporter.files(ProgressStage.DOWNLOADING_LIBRARIES, "progress.forge.legacy_libloader_download", index - 1, total)
                destination = libraries_dir / dependency.relative_path
                LegacyLibLoaderManager._acquire(dependency, destination, downloader, reporter)
                downloaded += 1
                resolved = destination.resolve(strict=False)
                if resolved not in processed_sources:
                    processed_sources.add(resolved)
                    new_sources.append(destination)
            if reporter is not None:
                reporter.files(ProgressStage.DOWNLOADING_LIBRARIES, "progress.forge.legacy_libloader_download", total, total)
            if not new_sources:
                break
            for key, dependency in LegacyLibLoaderManager._collect_dependencies(new_sources).items():
                if not LegacyLibLoaderManager._manageable(dependency):
                    continue
                current = dependencies.get(key)
                if current is None or LegacyLibLoaderManager._sort_key(dependency) > LegacyLibLoaderManager._sort_key(current):
                    dependencies[key] = dependency
        else:
            raise RuntimeError("Legacy LibLoader dependency resolution exceeded the safety round limit.")

        unresolved = [dependency.display_name for dependency in dependencies.values() if not LegacyLibLoaderManager._valid(libraries_dir / dependency.relative_path, dependency.sha512)]
        if unresolved:
            raise RuntimeError("Could not prepare legacy LibLoader dependencies: " + ", ".join(sorted(unresolved)))
        return (tr("warning.forge.legacy_libloader_recovered", "Recovered {count} legacy Forge mod library file(s).", count=downloaded),) if downloaded else ()

    @staticmethod
    def _collect_dependencies(sources: list[Path]) -> dict[str, LegacyLibLoaderDependency]:
        selected: dict[str, LegacyLibLoaderDependency] = {}
        for source in sources:
            try:
                attributes = LegacyLibLoaderManager._manifest_attributes(source)
            except (OSError, BadZipFile, KeyError):
                continue
            for index in range(256):
                prefix = f"libloader-"
                group = attributes.get(f"{prefix}group{index}", "").strip()
                if not group:
                    break
                sha512 = attributes.get(f"{prefix}sha512hash{index}", "").strip().casefold()
                if not _SHA512_PATTERN.fullmatch(sha512):
                    continue
                name = attributes.get(f"{prefix}name{index}", "").strip()
                version = attributes.get(f"{prefix}version{index}", "").strip()
                if not name or not version:
                    continue
                try:
                    build_time = int(attributes.get(f"{prefix}buildtime{index}", "0") or 0)
                except ValueError:
                    build_time = 0
                dependency = LegacyLibLoaderDependency(
                    group=group,
                    name=name,
                    version=version,
                    sha512=sha512,
                    source_jar=source,
                    classifier=attributes.get(f"{prefix}classifier{index}", "").strip(),
                    url=attributes.get(f"{prefix}url{index}", "").strip(),
                    embedded_file=attributes.get(f"{prefix}file{index}", "").strip(),
                    build_time=build_time,
                )
                current = selected.get(dependency.key)
                if current is None or LegacyLibLoaderManager._sort_key(dependency) > LegacyLibLoaderManager._sort_key(current):
                    selected[dependency.key] = dependency
        return selected

    @staticmethod
    def _manageable(dependency: LegacyLibLoaderDependency) -> bool:
        if dependency.embedded_file:
            return True
        parsed = urlparse(dependency.url)
        host = (parsed.hostname or "").casefold()
        return (parsed.scheme.casefold() == "https" and host in _ALLOWED_SOURCE_HOSTS) or (dependency.group, dependency.name, dependency.version) in _TACKPROFILER_COORDINATES

    @staticmethod
    def _manifest_attributes(source: Path) -> dict[str, str]:
        with ZipFile(source) as archive:
            payload = archive.read(_MANIFEST_NAME)
        text = payload.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
        logical_lines: list[str] = []
        for line in text.split("\n"):
            if line.startswith(" ") and logical_lines:
                logical_lines[-1] += line[1:]
            else:
                logical_lines.append(line)
        attributes: dict[str, str] = {}
        for line in logical_lines:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            attributes[key.strip().casefold()] = value.lstrip()
        return attributes

    @staticmethod
    def _acquire(dependency: LegacyLibLoaderDependency, destination: Path, service: ArtifactDownloadService, reporter: ProgressReporter | None) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if dependency.embedded_file:
            LegacyLibLoaderManager._extract_embedded(dependency, destination)
            return
        urls = LegacyLibLoaderManager._candidate_urls(dependency)
        if not urls:
            raise RuntimeError(f"No safe download source is available for legacy LibLoader dependency '{dependency.display_name}'.")
        request = ArtifactRequest(
            provider="legacy-libloader",
            purpose="forge-runtime-library",
            destination=destination,
            urls=urls,
            expected_filename=destination.name,
            hashes={"sha512": dependency.sha512},
            max_attempts=2,
            timeout=20.0,
            headers={"User-Agent": MODRINTH_USER_AGENT},
            max_bytes=_MAX_LIBRARY_BYTES,
            operation_id=f"legacy-libloader:{dependency.key}:{dependency.version}",
        )
        try:
            service.download(request, reporter=reporter, progress_stage=ProgressStage.DOWNLOADING_LIBRARIES, progress_message="progress.forge.legacy_libloader_download")
        except ArtifactDownloadError as error:
            raise RuntimeError(f"Could not recover legacy Forge library '{dependency.display_name}': {error.failure.detail}") from error

    @staticmethod
    def _extract_embedded(dependency: LegacyLibLoaderDependency, destination: Path) -> None:
        with ZipFile(dependency.source_jar) as archive:
            info = archive.getinfo(dependency.embedded_file)
            if info.file_size > _MAX_LIBRARY_BYTES:
                raise RuntimeError(f"Embedded legacy Forge library '{dependency.display_name}' exceeds the safety size limit.")
            payload = archive.read(info)
        if hashlib.sha512(payload).hexdigest() != dependency.sha512:
            raise RuntimeError(f"Embedded legacy Forge library '{dependency.display_name}' failed SHA-512 verification.")
        temporary = destination.with_name(destination.name + ".part")
        temporary.write_bytes(payload)
        temporary.replace(destination)

    @staticmethod
    def _candidate_urls(dependency: LegacyLibLoaderDependency) -> tuple[str, ...]:
        urls: list[str] = []
        parsed = urlparse(dependency.url)
        if parsed.scheme.casefold() == "https" and (parsed.hostname or "").casefold() in _ALLOWED_SOURCE_HOSTS:
            urls.append(dependency.url)
            path = parsed.path.lstrip("/")
            if path.casefold().startswith("maven2/"):
                path = path[len("maven2/"):]
            if path:
                urls.extend((f"https://repo1.maven.org/maven2/{path}", f"https://repo.maven.apache.org/maven2/{path}"))
        if (dependency.group, dependency.name, dependency.version) in _TACKPROFILER_COORDINATES:
            urls.append(f"{_TACKPROFILER_BASE}/{dependency.mirror_filename}")
        return tuple(dict.fromkeys(urls))

    @staticmethod
    def _valid(path: Path, expected_sha512: str) -> bool:
        try:
            if not path.is_file() or path.stat().st_size > _MAX_LIBRARY_BYTES:
                return False
            digest = hashlib.sha512()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest() == expected_sha512
        except OSError:
            return False

    @staticmethod
    def _sort_key(dependency: LegacyLibLoaderDependency) -> tuple[tuple[int, ...], int, str, int]:
        version, _, suffix = dependency.version.partition("-")
        try:
            raw_numbers = tuple(int(part) for part in version.split("."))
        except ValueError:
            raw_numbers = (0,)
        numbers = (raw_numbers + (0,) * 8)[:8]
        suffix_key = suffix.casefold().strip()
        suffix_rank = {"alpha": -3, "beta": -2, "snapshot": -2, "": 0}.get(suffix_key, -1)
        return numbers, suffix_rank, suffix_key, dependency.build_time
