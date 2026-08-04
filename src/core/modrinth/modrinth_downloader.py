from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
import hashlib

import httpx

from src.config import MODRINTH_USER_AGENT
from src.core.network.download_bandwidth_limiter import download_bandwidth_limiter  # shared singleton; retained for compatibility
from src.core.network.download_manager import download_manager
from src.core.network.artifact_download_service import artifact_download_service
from src.core.network.httpx_downloader import HttpDownloader
from src.core.progress.progress_reporter import ProgressReporter
from src.models.modrinth.version import ModrinthFile
from src.models.network.artifact import ArtifactRequest
from src.models.progress.progress_stage import ProgressStage


class ModrinthDownloader:
    ALLOWED_PACK_HOSTS = {
        "cdn.modrinth.com",
        "github.com",
        "raw.githubusercontent.com",
        "objects.githubusercontent.com",
        "github-releases.githubusercontent.com",
        "gitlab.com",
        "assets.gitlab-static.net",
        "maven.fabricmc.net",
        "repo1.maven.org",
    }
    RETRYABLE_STATUS_CODES = HttpDownloader.RETRYABLE_STATUS_CODES
    DEFAULT_TIMEOUT = httpx.Timeout(connect=20.0, read=90.0, write=30.0, pool=30.0)

    @staticmethod
    def download_file(file: ModrinthFile, destination: Path, force: bool = False, reporter: ProgressReporter | None = None, progress_stage: ProgressStage = ProgressStage.DOWNLOADING_MODS, progress_message: str | None = None, max_retry: int = 5, purpose: str = "mod", page_url: str = "", project_url: str = "", project_id: str = "", version_id: str = "") -> Path:
        return ModrinthDownloader.download_urls(
            urls=(file.url,),
            destination=destination,
            sha1=file.sha1,
            sha512=file.sha512,
            expected_size=file.size,
            force=force,
            restrict_hosts=False,
            max_retry=max_retry,
            reporter=reporter,
            progress_stage=progress_stage,
            progress_message=progress_message,
            purpose=purpose,
            page_url=page_url,
            project_url=project_url,
            project_id=project_id,
            version_id=version_id,
        )

    @staticmethod
    def download_urls(urls: tuple[str, ...] | list[str], destination: Path, sha1: str = "", sha512: str = "", expected_size: int = 0, force: bool = False, restrict_hosts: bool = True, max_retry: int = 5, reporter: ProgressReporter | None = None, progress_stage: ProgressStage = ProgressStage.DOWNLOADING_MODS, progress_message: str | None = None, purpose: str = "artifact", page_url: str = "", project_url: str = "", project_id: str = "", version_id: str = "", file_id: str = "") -> Path:
        normalized_urls = tuple(dict.fromkeys(str(url).strip() for url in urls if str(url).strip()))
        if restrict_hosts:
            accepted: list[str] = []
            last_error: RuntimeError | None = None
            for url in normalized_urls:
                try:
                    ModrinthDownloader._validate_pack_url(url)
                except RuntimeError as error:
                    last_error = error
                else:
                    accepted.append(url)
            normalized_urls = tuple(accepted)
            if not normalized_urls and last_error is not None:
                raise last_error

        hashes = {}
        if sha1:
            hashes["sha1"] = sha1
        if sha512:
            hashes["sha512"] = sha512
        request = ArtifactRequest(
            provider="modrinth",
            purpose=purpose,
            destination=destination,
            urls=normalized_urls,
            page_url=page_url,
            project_url=project_url,
            expected_filename=destination.name,
            expected_size=max(0, int(expected_size or 0)),
            hashes=hashes,
            project_id=project_id,
            version_id=version_id,
            file_id=file_id,
            max_attempts=max_retry,
            timeout=ModrinthDownloader.DEFAULT_TIMEOUT,
            headers={"User-Agent": MODRINTH_USER_AGENT},
            force=force,
        )
        return artifact_download_service.download(
            request,
            reporter=reporter,
            progress_stage=progress_stage,
            progress_message=progress_message or f"Downloading {destination.name}...",
            client_provider=HttpDownloader.get_client,
        ).path

    @staticmethod
    def _hash_partial(path: Path, expected_size: int):
        sha1_hash = hashlib.sha1(usedforsecurity=False)
        sha512_hash = hashlib.sha512()
        if not path.is_file():
            return 0, sha1_hash, sha512_hash
        try:
            size = path.stat().st_size
            if expected_size > 0 and size > expected_size:
                path.unlink(missing_ok=True)
                return 0, sha1_hash, sha512_hash
            with path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    sha1_hash.update(chunk)
                    sha512_hash.update(chunk)
            return size, sha1_hash, sha512_hash
        except OSError:
            path.unlink(missing_ok=True)
            return 0, hashlib.sha1(usedforsecurity=False), hashlib.sha512()

    @staticmethod
    def verify(path: Path, sha1: str = "", sha512: str = "", expected_size: int = 0) -> bool:
        hashes = {}
        if sha1:
            hashes["sha1"] = sha1
        if sha512:
            hashes["sha512"] = sha512
        return bool(hashes) and download_manager.verify(path, max(0, int(expected_size or 0)), hashes)

    @staticmethod
    def _validate_digest(name: str, size: int, actual_sha1: str, actual_sha512: str, expected_sha1: str, expected_sha512: str, expected_size: int) -> None:
        if expected_size > 0 and size != expected_size:
            raise RuntimeError(f"Size mismatch for '{name}'.")
        if expected_sha1 and actual_sha1.lower() != expected_sha1.lower():
            raise RuntimeError(f"SHA-1 mismatch for '{name}'.")
        if expected_sha512 and actual_sha512.lower() != expected_sha512.lower():
            raise RuntimeError(f"SHA-512 mismatch for '{name}'.")

    @staticmethod
    def _validate_pack_url(url: str) -> None:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme.lower() != "https":
            raise RuntimeError("Modpack files must use HTTPS URLs.")
        if not host or parsed.username or parsed.password:
            raise RuntimeError("Modpack download URL is invalid.")
        if host not in ModrinthDownloader.ALLOWED_PACK_HOSTS:
            raise RuntimeError(f"Modpack download host is not allowed: {host}")

    @staticmethod
    def _report(reporter: ProgressReporter | None, stage: ProgressStage, message: str, current: int, total: int, bytes_per_second: float | None = None) -> None:
        if reporter is not None:
            reporter.bytes(stage=stage, message=message, current=max(0, current), total=max(0, total), bytes_per_second=bytes_per_second)
