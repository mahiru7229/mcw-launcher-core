from __future__ import annotations

from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
import ipaddress
import socket
import hashlib
import json
import os
import shutil

from src.core.curseforge.curseforge_client import CurseForgeClient
from src.core.curseforge.curseforge_downloader import CurseForgeDownloader, CurseForgeManualDownloadRequired
from src.core.modrinth.modrinth_client import ModrinthClient
from src.core.modrinth.modrinth_downloader import ModrinthDownloader
from src.core.network.download_pause import DownloadCancelledError, DownloadPausedError
from src.core.progress.progress_reporter import ProgressReporter
from src.models.instance.instance import Instance
from src.models.package.portable_manual_download import PortableManualDownload
from src.models.progress.progress_stage import ProgressStage


class PortableManualDownloadRequired(RuntimeError):
    def __init__(self, instance: Instance, requirements: tuple[PortableManualDownload, ...]) -> None:
        self.instance = instance
        self.requirements = tuple(requirements)
        super().__init__(f"{len(self.requirements)} portable-modpack file(s) require manual download.")


class PortableContentManager:
    FILE_NAME = "manual-files.json"
    REFERENCED_FILE_NAME = "portable-referenced-files.json"
    DISABLED_FILE_NAME = "portable-disabled-files.json"
    COPY_CHUNK_SIZE = 1024 * 1024

    @staticmethod
    def ensure(instance: Instance) -> None:
        instance_dir = getattr(instance, "instance_dir", None)
        if instance_dir is None:
            return
        registry_path = Path(instance_dir) / ".mcw" / PortableContentManager.FILE_NAME
        data = PortableContentManager._load_registry(registry_path)
        files = data.get("files") if isinstance(data.get("files"), list) else []
        missing: list[PortableManualDownload] = []
        retained: list[dict] = []
        for raw in files:
            if not isinstance(raw, dict):
                continue
            target = PortableContentManager._target(Path(instance_dir), raw.get("targetPath"))
            hashes = raw.get("hashes") if isinstance(raw.get("hashes"), dict) else {}
            if target is not None and PortableContentManager._verify(target, max(0, int(raw.get("size", 0) or 0)), hashes):
                continue
            retained.append(raw)
            missing.append(PortableContentManager._requirement(raw))
        if not missing:
            registry_path.unlink(missing_ok=True)
            return
        if retained != files:
            PortableContentManager._save_registry(registry_path, retained)
        raise PortableManualDownloadRequired(instance, tuple(missing))


    @staticmethod
    def prefetch_referenced(instance: Instance, reporter: ProgressReporter | None = None) -> None:
        instance_dir = getattr(instance, "instance_dir", None)
        if instance_dir is None:
            return
        root = Path(instance_dir)
        registry_path = root / ".mcw" / PortableContentManager.REFERENCED_FILE_NAME
        data = PortableContentManager._load_registry(registry_path)
        files = data.get("files") if isinstance(data.get("files"), list) else []
        remaining: list[dict] = []
        total = len(files)
        for index, raw in enumerate(files, start=1):
            if not isinstance(raw, dict):
                continue
            declared_target = PortableContentManager._target(root, raw.get("targetPath"))
            if declared_target is None:
                continue
            hashes = raw.get("hashes") if isinstance(raw.get("hashes"), dict) else {}
            size = max(0, int(raw.get("size", 0) or 0))
            if PortableContentManager._verify(declared_target, size, hashes):
                continue
            target = declared_target
            if target.name.casefold().endswith(".disabled"):
                target = target.with_name(target.name[:-len(".disabled")])
            if PortableContentManager._verify(target, size, hashes):
                continue
            sources = raw.get("sources") if isinstance(raw.get("sources"), list) else []
            sources = sorted((source for source in sources if isinstance(source, dict)), key=lambda source: (max(1, int(source.get("priority", 1000) or 1000)), str(source.get("provider") or "")))
            downloaded = False
            for source in sources:
                try:
                    PortableContentManager._download_source(source, raw, target, reporter)
                except (DownloadCancelledError, DownloadPausedError):
                    raise
                except (CurseForgeManualDownloadRequired, OSError, RuntimeError, ValueError):
                    target.unlink(missing_ok=True)
                    target.with_name(target.name + ".part").unlink(missing_ok=True)
                    continue
                if PortableContentManager._verify(target, size, hashes):
                    downloaded = True
                    break
                target.unlink(missing_ok=True)
            if not downloaded:
                remaining.append(raw)
            if reporter is not None:
                reporter.files(ProgressStage.DOWNLOADING_MODS, "Downloading modpack mods...", index, total)
        if remaining:
            PortableContentManager._save_registry(registry_path, remaining)
        else:
            registry_path.unlink(missing_ok=True)

    @staticmethod
    def _download_source(source: dict, entry: dict, target: Path, reporter: ProgressReporter | None) -> None:
        provider = str(source.get("provider") or "direct").strip().casefold()
        hashes = entry.get("hashes") if isinstance(entry.get("hashes"), dict) else {}
        sha1 = str(hashes.get("sha1") or "").strip().casefold()
        sha512 = str(hashes.get("sha512") or "").strip().casefold()
        size = max(0, int(entry.get("size", 0) or 0))
        filename = Path(str(entry.get("fileName") or target.name)).name
        project_id = str(source.get("projectId") or "").strip()
        version_id = str(source.get("versionId") or "").strip()
        file_id = str(source.get("fileId") or "").strip()
        if provider == "modrinth" and version_id:
            version = ModrinthClient.get_version(version_id)
            candidates = [file for file in version.files if PortableContentManager._modrinth_file_matches(file, filename, size, sha1, sha512)]
            if not candidates:
                raise RuntimeError("The Modrinth source does not provide the exact manifest file.")
            ModrinthDownloader.download_file(candidates[0], target, reporter=reporter, progress_stage=ProgressStage.DOWNLOADING_MODS, progress_message="Downloading modpack mods...", purpose="portable-mod", project_id=project_id or version.project_id, version_id=version.version_id)
            return
        if provider == "curseforge" and project_id and file_id:
            file = CurseForgeClient.get_file(project_id, file_id)
            if not PortableContentManager._curseforge_file_matches(file, filename, size, sha1):
                raise RuntimeError("The CurseForge source does not provide the exact manifest file.")
            CurseForgeDownloader.download_file(file, target, reporter=reporter, stage=ProgressStage.DOWNLOADING_MODS, message="Downloading modpack mods...", purpose="portable-mod", managed_kind="mod", managed_path=str(entry.get("targetPath") or f"mods/{filename}"))
            return
        urls = PortableContentManager._safe_public_urls(source.get("urls"))
        if not urls or not (sha1 or sha512):
            raise RuntimeError("This source cannot be verified or downloaded automatically.")
        ModrinthDownloader.download_urls(urls, target, sha1=sha1, sha512=sha512, expected_size=size, force=False, restrict_hosts=False, reporter=reporter, progress_stage=ProgressStage.DOWNLOADING_MODS, progress_message="Downloading modpack mods...", purpose="portable-mod", project_id=project_id, version_id=version_id, file_id=file_id)

    @staticmethod
    def _modrinth_file_matches(file, filename: str, size: int, sha1: str, sha512: str) -> bool:
        if sha512 and str(getattr(file, "sha512", "")).casefold() != sha512:
            return False
        if sha1 and str(getattr(file, "sha1", "")).casefold() != sha1:
            return False
        if size > 0 and int(getattr(file, "size", 0) or 0) != size:
            return False
        return bool(sha1 or sha512) or str(getattr(file, "filename", "")).casefold() == filename.casefold()

    @staticmethod
    def _curseforge_file_matches(file, filename: str, size: int, sha1: str) -> bool:
        if sha1 and str(getattr(file, "sha1", "")).casefold() != sha1:
            return False
        if size > 0 and int(getattr(file, "file_length", 0) or 0) != size:
            return False
        return bool(sha1) or str(getattr(file, "file_name", "")).casefold() == filename.casefold()

    @staticmethod
    def _safe_public_urls(values: object) -> tuple[str, ...]:
        if not isinstance(values, (list, tuple)):
            return ()
        output: list[str] = []
        for value in values:
            url = str(value or "").strip()
            try:
                parsed = urlparse(url)
            except ValueError:
                continue
            host = str(parsed.hostname or "").strip().casefold()
            if parsed.scheme.casefold() != "https" or not host or parsed.username or parsed.password or host == "localhost" or host.endswith(".localhost"):
                continue
            try:
                literal = ipaddress.ip_address(host)
            except ValueError:
                literal = None
            if literal is not None and not literal.is_global:
                continue
            if literal is None:
                try:
                    addresses = {ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
                except (OSError, ValueError):
                    continue
                if not addresses or any(not address.is_global for address in addresses):
                    continue
            if url not in output:
                output.append(url)
        return tuple(output)

    @staticmethod
    def finalize_disabled(instance: Instance) -> None:
        instance_dir = getattr(instance, "instance_dir", None)
        if instance_dir is None:
            return
        registry_path = Path(instance_dir) / ".mcw" / PortableContentManager.DISABLED_FILE_NAME
        data = PortableContentManager._load_registry(registry_path)
        files = data.get("files") if isinstance(data.get("files"), list) else []
        remaining: list[dict] = []
        for raw in files:
            if not isinstance(raw, dict):
                continue
            disabled_target = PortableContentManager._target(Path(instance_dir), raw.get("targetPath"))
            hashes = raw.get("hashes") if isinstance(raw.get("hashes"), dict) else {}
            size = max(0, int(raw.get("size", 0) or 0))
            if disabled_target is None:
                continue
            if PortableContentManager._verify(disabled_target, size, hashes):
                continue
            if not disabled_target.name.casefold().endswith(".disabled"):
                continue
            active_target = disabled_target.with_name(disabled_target.name[:-len(".disabled")])
            if not PortableContentManager._verify(active_target, size, hashes):
                remaining.append(raw)
                continue
            disabled_target.parent.mkdir(parents=True, exist_ok=True)
            disabled_target.unlink(missing_ok=True)
            active_target.replace(disabled_target)
        if remaining:
            PortableContentManager._save_registry(registry_path, remaining)
        else:
            registry_path.unlink(missing_ok=True)

    @staticmethod
    def install_many(instance: Instance, requirements: tuple[PortableManualDownload, ...] | list[PortableManualDownload], sources: tuple[Path, ...] | list[Path]) -> tuple[str, ...]:
        pending = list(requirements)
        candidates = [Path(source) for source in sources if Path(source).is_file()]
        if not pending or not candidates:
            raise RuntimeError("Select the files downloaded from the official project pages.")
        installed: list[str] = []
        used: set[Path] = set()
        for requirement in pending:
            matches = [source for source in candidates if source not in used and PortableContentManager._matches(source, requirement)]
            if not matches:
                raise RuntimeError(f"No selected file matches '{requirement.file_name}'. Check its size and checksum.")
            if len(matches) > 1:
                exact = [source for source in matches if source.name.casefold() == requirement.file_name.casefold()]
                if len(exact) == 1:
                    matches = exact
                else:
                    raise RuntimeError(f"More than one selected file matches '{requirement.file_name}'. Select only the official file.")
            source = matches[0]
            target = PortableContentManager._target(Path(instance.instance_dir), requirement.managed_path)
            if target is None:
                raise RuntimeError(f"Unsafe portable-modpack target path: {requirement.managed_path}")
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(target.suffix + ".part")
            try:
                temporary.unlink(missing_ok=True)
                with source.open("rb") as input_stream, temporary.open("wb") as output_stream:
                    shutil.copyfileobj(input_stream, output_stream, length=PortableContentManager.COPY_CHUNK_SIZE)
                    output_stream.flush()
                    os.fsync(output_stream.fileno())
                if not PortableContentManager._verify(temporary, requirement.file_size, {"sha1": requirement.sha1, "sha512": requirement.sha512}):
                    raise RuntimeError(f"The selected file does not match '{requirement.file_name}'.")
                temporary.replace(target)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
            used.add(source)
            installed.append(requirement.managed_path)
        PortableContentManager._remove_installed(instance, set(installed))
        return tuple(installed)

    @staticmethod
    def _requirement(raw: dict) -> PortableManualDownload:
        provider = str(raw.get("provider") or "manual").strip().casefold() or "manual"
        filename = Path(str(raw.get("fileName") or Path(str(raw.get("targetPath") or "download.jar")).name)).name
        hashes = raw.get("hashes") if isinstance(raw.get("hashes"), dict) else {}
        project_id = str(raw.get("projectId") or "").strip()
        version_id = str(raw.get("versionId") or "").strip()
        file_id = str(raw.get("fileId") or version_id).strip()
        return PortableManualDownload(
            provider=provider,
            project_id=project_id,
            file_id=file_id,
            version_id=version_id,
            project_name=str(raw.get("projectName") or filename).strip(),
            file_name=filename,
            file_size=max(0, int(raw.get("size", 0) or 0)),
            sha1=str(hashes.get("sha1") or "").strip().casefold(),
            sha512=str(hashes.get("sha512") or "").strip().casefold(),
            project_url=str(raw.get("projectUrl") or "").strip(),
            version_url=str(raw.get("versionUrl") or "").strip(),
            direct_url="",
            reason=str(raw.get("reason") or "The provider file cannot be downloaded automatically or redistribution is not permitted.").strip(),
            managed_kind="mod",
            managed_path=str(raw.get("targetPath") or f"mods/{filename}").replace("\\", "/").strip("/"),
        )

    @staticmethod
    def _target(instance_dir: Path, value: object) -> Path | None:
        normalized = str(value or "").replace("\\", "/").strip().strip("/")
        relative = PurePosixPath(normalized)
        if not normalized or relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            return None
        lowered = relative.name.casefold()
        if not relative.parts or relative.parts[0].casefold() != "mods" or not (lowered.endswith(".jar") or lowered.endswith(".jar.disabled")):
            return None
        return instance_dir.joinpath(*relative.parts)

    @staticmethod
    def _load_registry(path: Path) -> dict:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
            return {"schemaVersion": 1, "files": []}
        return data if isinstance(data, dict) else {"schemaVersion": 1, "files": []}

    @staticmethod
    def _save_registry(path: Path, files: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".part")
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps({"schemaVersion": 1, "files": files}, indent=2, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)

    @staticmethod
    def _remove_installed(instance: Instance, installed_paths: set[str]) -> None:
        registry_path = Path(instance.instance_dir) / ".mcw" / PortableContentManager.FILE_NAME
        data = PortableContentManager._load_registry(registry_path)
        files = data.get("files") if isinstance(data.get("files"), list) else []
        remaining = [raw for raw in files if isinstance(raw, dict) and str(raw.get("targetPath") or "").replace("\\", "/").strip("/") not in installed_paths]
        if remaining:
            PortableContentManager._save_registry(registry_path, remaining)
        else:
            registry_path.unlink(missing_ok=True)

    @staticmethod
    def _matches(path: Path, requirement: PortableManualDownload) -> bool:
        hashes = {"sha1": requirement.sha1, "sha512": requirement.sha512}
        if requirement.sha1 or requirement.sha512:
            return PortableContentManager._verify(path, requirement.file_size, hashes)
        try:
            size_matches = requirement.file_size <= 0 or path.stat().st_size == requirement.file_size
        except OSError:
            return False
        return size_matches and path.name.casefold() == requirement.file_name.casefold()

    @staticmethod
    def _verify(path: Path, expected_size: int, hashes: dict) -> bool:
        try:
            if not path.is_file() or (expected_size > 0 and path.stat().st_size != expected_size):
                return False
        except OSError:
            return False
        expected_sha512 = str(hashes.get("sha512") or "").strip().casefold()
        expected_sha1 = str(hashes.get("sha1") or "").strip().casefold()
        if not expected_sha512 and not expected_sha1:
            return True
        sha512 = hashlib.sha512() if expected_sha512 else None
        sha1 = hashlib.sha1(usedforsecurity=False) if expected_sha1 else None
        try:
            with path.open("rb") as stream:
                while chunk := stream.read(PortableContentManager.COPY_CHUNK_SIZE):
                    if sha512 is not None:
                        sha512.update(chunk)
                    if sha1 is not None:
                        sha1.update(chunk)
        except OSError:
            return False
        return (sha512 is None or sha512.hexdigest().casefold() == expected_sha512) and (sha1 is None or sha1.hexdigest().casefold() == expected_sha1)
