
from pathlib import Path, PurePosixPath
import concurrent.futures
import json
import shutil
import stat
import zipfile

from src.core.fs.paths import Paths
from src.core.minecraft.library_rule_manager import LibraryRuleManager
from src.core.minecraft.metadata_validation import MinecraftMetadataValidation
from src.core.network.httpx_downloader import HttpDownloader
from src.core.progress.file_batch_progress import FileBatchProgress
from src.core.progress.progress_reporter import ProgressReporter
from src.core.repair.verification_cache import VerificationCache
from src.models.minecraft.library import DownloadLibrary
from src.models.minecraft.version import Version
from src.models.progress.progress_stage import ProgressStage


MAX_WORKERS = 20


class DownloadLibraryManager:

    @staticmethod
    def load(
        version: Version,
        reporter: ProgressReporter | None = None,
        verification_cache: VerificationCache | None = None,
        fast_verify: bool = False,
    ) -> list[Path]:
        library_data = DownloadLibraryManager._load_download(
            version.path
        )

        libraries = DownloadLibraryManager._load_download_object(
            library_data
        )

        downloaded_paths: list[Path] = []

        total = len(libraries)

        batch_progress = FileBatchProgress(reporter=reporter, stage=ProgressStage.DOWNLOADING_LIBRARIES, message="Preparing Minecraft libraries...", total=total, min_emit_interval_seconds=0.08)
        batch_progress.start()

        if total == 0:
            return downloaded_paths

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=MAX_WORKERS
        ) as executor:
            future_to_library = {}
            for library in libraries:
                token = object()
                child_reporter = batch_progress.reporter_for(token)
                if verification_cache is None and not fast_verify:
                    future = executor.submit(DownloadLibraryManager._download_single_library, library, version) if child_reporter is None else executor.submit(DownloadLibraryManager._download_single_library, library, version, child_reporter)
                else:
                    future = executor.submit(
                        DownloadLibraryManager._download_single_library,
                        library,
                        version,
                        child_reporter,
                        verification_cache,
                        fast_verify,
                    )
                future_to_library[future] = (library, token)

            for future in concurrent.futures.as_completed(
                future_to_library
            ):
                library, token = future_to_library[future]

                try:
                    library_path = future.result()
                    downloaded_paths.append(library_path)

                except Exception as error:
                    batch_progress.discard(token)
                    raise RuntimeError(
                        "Failed to download library: "
                        f"{library.path}"
                    ) from error

                batch_progress.complete(token)


        return downloaded_paths

    @staticmethod
    def _download_single_library(
        library: DownloadLibrary,
        version: Version,
        reporter: ProgressReporter | None = None,
        verification_cache: VerificationCache | None = None,
        fast_verify: bool = False,
    ) -> Path:
        library_path = Paths.libraries() / library.path

        valid = False
        if library_path.exists():
            if verification_cache is not None:
                verification = verification_cache.verify(
                    "library:" + library.path.as_posix(),
                    library_path,
                    library.size,
                    library.sha1,
                    "sha1",
                    force_hash=not fast_verify,
                )
                valid = verification.valid
            else:
                valid = HttpDownloader.verify_sha1(library_path, library.sha1)

        if valid:
            if library.is_native:
                DownloadLibraryManager._extract_native(
                    native_path=library_path,
                    version=version,
                    sha1=library.sha1,
                )
            return library_path

        HttpDownloader.delete_file(library_path)

        kwargs = {"download_info": library, "path": library_path, "max_retry": 5}
        if reporter is not None:
            kwargs.update({"reporter": reporter, "progress_stage": ProgressStage.DOWNLOADING_LIBRARIES, "progress_message": f"Downloading library {library_path.name}..."})
        downloaded_path = HttpDownloader.download(**kwargs)
        if verification_cache is not None:
            verification_cache.verify(
                "library:" + library.path.as_posix(),
                downloaded_path,
                library.size,
                library.sha1,
                "sha1",
                force_hash=True,
            )

        if library.is_native:
            DownloadLibraryManager._extract_native(
                native_path=downloaded_path,
                version=version,
                sha1=library.sha1,
            )

        return downloaded_path

    @staticmethod
    def _load_download(path: Path) -> dict:
        try:
            return json.loads(
                path.read_text(encoding="utf-8")
            )

        except (
            FileNotFoundError,
            json.JSONDecodeError,
        ):
            return {}

    @staticmethod
    def _extract_native(
        native_path: Path,
        version: Version,
        sha1: str,
    ) -> None:
        destination = Paths.natives(version)
        marker_dir = destination / ".extracted"
        marker_path = marker_dir / sha1

        if marker_path.exists():
            return

        destination.mkdir(
            parents=True,
            exist_ok=True,
        )

        marker_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        with zipfile.ZipFile(native_path, "r") as archive:
            for member in archive.infolist():
                relative = DownloadLibraryManager._safe_native_path(member)
                if relative is None:
                    continue

                target = destination.joinpath(*relative.parts)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue

                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member, "r") as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)

        marker_path.touch()

    @staticmethod
    def _safe_native_path(member: zipfile.ZipInfo) -> PurePosixPath | None:
        normalized = str(member.filename).replace("\\", "/").strip()
        if not normalized:
            return None
        path = PurePosixPath(normalized)
        if path.parts and path.parts[0].casefold() == "meta-inf":
            return None
        if stat.S_ISLNK((member.external_attr >> 16) & 0xFFFF):
            raise RuntimeError(f"Native archive contains a symbolic link: {member.filename}")
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise RuntimeError(f"Unsafe path in native archive: {member.filename}")
        if not path.parts or ":" in path.parts[0] or path.parts[0].casefold() == ".extracted":
            raise RuntimeError(f"Unsafe path in native archive: {member.filename}")
        return path

    @staticmethod
    def _load_download_object(
        download_dict: dict,
    ) -> list[DownloadLibrary]:
        libraries: list[DownloadLibrary] = []

        for download in download_dict.get(
            "libraries",
            [],
        ):
            if not LibraryRuleManager.is_allowed(download):
                continue

            downloads = download.get(
                "downloads",
                {},
            )

            artifact = downloads.get("artifact")

            if isinstance(artifact, dict):
                libraries.append(DownloadLibraryManager._parse_library(artifact, is_native=False))

            native_name = download.get(
                "natives",
                {},
            ).get(LibraryRuleManager._get_current_os())

            if not native_name:
                continue

            native_name = native_name.replace(
                "${arch}",
                "32" if LibraryRuleManager._get_current_arch() == "x86" else "64",
            )

            native_artifact = downloads.get(
                "classifiers",
                {},
            ).get(native_name)

            if not native_artifact:
                continue

            if not isinstance(native_artifact, dict):
                continue
            libraries.append(DownloadLibraryManager._parse_library(native_artifact, is_native=True))

        return libraries

    @staticmethod
    def _parse_library(data: dict, *, is_native: bool) -> DownloadLibrary:
        try:
            url = str(data["url"]).strip()
            sha1 = MinecraftMetadataValidation.sha1(data["sha1"], "library SHA-1")
            size = int(data["size"])
            path = MinecraftMetadataValidation.relative_path(data["path"], "library path")
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError("Invalid Minecraft library metadata.") from error
        if not url or size <= 0:
            raise RuntimeError("Invalid Minecraft library metadata.")
        return DownloadLibrary(url=url, sha1=sha1, size=size, path=path, is_native=is_native)
