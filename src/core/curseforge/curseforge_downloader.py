from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from src.core.curseforge.curseforge_client import CurseForgeClient
from src.core.curseforge.curseforge_download_fallback import CurseForgeDownloadFallback
from src.core.curseforge.curseforge_links import file_page_url, is_numeric_project_placeholder, normalize_project_page, project_search_url
from src.core.network.artifact_download_service import ArtifactDownloadError, artifact_download_service
from src.core.network.httpx_downloader import HttpDownloader
from src.core.progress.progress_reporter import ProgressReporter
from src.models.curseforge.file import CurseForgeFile
from src.models.curseforge.manual_download import CurseForgeManualDownload
from src.models.network.artifact import ArtifactDownloadFailure, ArtifactRequest
from src.models.progress.progress_stage import ProgressStage


class CurseForgeManualDownloadRequired(RuntimeError):
    def __init__(self, requirement: CurseForgeManualDownload) -> None:
        super().__init__(requirement.reason)
        self.requirement = requirement


class CurseForgeDownloader:
    @staticmethod
    def download_file(file: CurseForgeFile, destination: Path, reporter: ProgressReporter | None = None, stage: ProgressStage = ProgressStage.DOWNLOADING_MODS, message: str | None = None, project_name: str = "", purpose: str = "mod", managed_kind: str = "mod", managed_path: str = "", project_url: str = "") -> Path:
        resolved = file
        gateway_error: RuntimeError | None = None
        if not resolved.download_url and resolved.is_available:
            try:
                download_url = CurseForgeClient.get_download_url(resolved.project_id, resolved.file_id, force_refresh=True)
            except RuntimeError as error:
                gateway_error = error
                download_url = ""
            resolved = replace(resolved, download_url=download_url)

        if not resolved.download_url and resolved.sha1:
            fallback = CurseForgeDownloadFallback.find_exact_hash_mirror(resolved.sha1, expected_name=resolved.file_name, expected_size=resolved.file_length)
            if fallback is not None:
                resolved = replace(
                    resolved,
                    download_url=fallback.url,
                    file_name=fallback.file_name or resolved.file_name,
                    file_length=fallback.size or resolved.file_length,
                    is_available=True,
                )

        name = str(project_name).strip() or f"CurseForge project {resolved.project_id}"
        canonical_project_url = CurseForgeDownloader._resolve_project_url(resolved.project_id, project_url)
        version_url = file_page_url(canonical_project_url, resolved.file_id)
        hashes = {"sha1": resolved.sha1} if resolved.sha1 else {}
        request = ArtifactRequest(
            provider="curseforge",
            purpose=purpose,
            destination=destination,
            urls=(resolved.download_url,) if resolved.download_url else (),
            page_url=version_url,
            project_url=canonical_project_url,
            expected_filename=resolved.file_name,
            expected_size=resolved.file_length,
            hashes=hashes,
            project_id=str(resolved.project_id),
            file_id=str(resolved.file_id),
            max_attempts=5,
            timeout=60.0,
        )

        if not resolved.is_available:
            unavailable_request = replace(request, urls=())
            failure = artifact_download_service.failure(unavailable_request, RuntimeError("No download URL is available because third-party distribution is disabled."))
            raise CurseForgeManualDownloadRequired(CurseForgeDownloader._manual_requirement(resolved, name, failure, managed_kind, managed_path, gateway_error))

        if not resolved.sha1:
            failure = artifact_download_service.failure(request, RuntimeError(f"CurseForge file '{resolved.file_name}' does not provide a SHA-1 hash."))
            raise CurseForgeManualDownloadRequired(CurseForgeDownloader._manual_requirement(resolved, name, failure, managed_kind, managed_path, gateway_error))

        try:
            return artifact_download_service.download(
                request,
                reporter=reporter,
                progress_stage=stage,
                progress_message=message or f"Downloading {resolved.file_name}...",
                client_provider=HttpDownloader.get_client,
            ).path
        except ArtifactDownloadError as error:
            raise CurseForgeManualDownloadRequired(CurseForgeDownloader._manual_requirement(resolved, name, error.failure, managed_kind, managed_path, gateway_error)) from error


    @staticmethod
    def _resolve_project_url(project_id: int, candidate: str = "") -> str:
        normalized = normalize_project_page(candidate)
        if normalized and not is_numeric_project_placeholder(normalized, project_id):
            return normalized
        try:
            project = CurseForgeClient.get_project(project_id)
        except RuntimeError:
            project = None
        resolved = normalize_project_page(getattr(project, "project_url", "")) if project is not None else ""
        if resolved and not is_numeric_project_placeholder(resolved, project_id):
            return resolved
        return project_search_url(project_id)

    @staticmethod
    def _manual_requirement(file: CurseForgeFile, project_name: str, failure: ArtifactDownloadFailure, managed_kind: str, managed_path: str, gateway_error: RuntimeError | None = None) -> CurseForgeManualDownload:
        details = failure.detail
        if gateway_error is not None and failure.reason.value == "NO_DOWNLOAD_URL":
            details = f"CurseForge gateway error: {gateway_error}. {details}"
        reason = (
            f"Automatic download failed ({failure.reason.value}): {details} "
            f"Download '{file.file_name}' manually, then choose it in MCW Launcher."
        )
        return CurseForgeManualDownload(
            project_id=file.project_id,
            file_id=file.file_id,
            project_name=project_name,
            file_name=file.file_name,
            file_size=file.file_length,
            sha1=file.sha1,
            project_url=failure.project_url or project_search_url(file.project_id),
            reason=reason,
            managed_kind=managed_kind,
            managed_path=managed_path,
            direct_url=failure.url,
            version_url=failure.page_url,
            failure_reason=failure.reason.value,
            http_status=failure.http_status,
            attempts=failure.attempts,
            retryable=failure.retryable,
        )
