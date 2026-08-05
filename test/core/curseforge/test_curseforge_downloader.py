from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.curseforge.curseforge_downloader import CurseForgeDownloader, CurseForgeManualDownloadRequired
from src.core.network.download_models import DownloadResult
from src.models.curseforge.file import CurseForgeFile


def make_file(**overrides) -> CurseForgeFile:
    values = dict(
        file_id=2,
        project_id=1,
        display_name="Example",
        file_name="example.jar",
        release_type="release",
        file_date="",
        file_length=10,
        download_url="https://example/example.jar",
        sha1="a" * 40,
        game_versions=("1.20.1",),
        dependencies=(),
        is_available=True,
    )
    values.update(overrides)
    return CurseForgeFile(**values)


def test_unavailable_file_returns_structured_manual_requirement(tmp_path: Path) -> None:
    with pytest.raises(CurseForgeManualDownloadRequired) as captured:
        CurseForgeDownloader.download_file(make_file(is_available=False), tmp_path / "example.jar", project_name="Example")

    requirement = captured.value.requirement
    assert requirement.project_name == "Example"
    assert requirement.file_name == "example.jar"
    assert requirement.sha1 == "a" * 40
    assert "third-party distribution" in requirement.reason


def test_missing_hash_is_rejected_before_download(tmp_path: Path) -> None:
    with pytest.raises(CurseForgeManualDownloadRequired, match="does not provide a SHA-1"):
        CurseForgeDownloader.download_file(make_file(sha1=""), tmp_path / "example.jar")


def test_missing_download_url_is_resolved_shortly_before_download(monkeypatch, tmp_path: Path) -> None:
    destination = tmp_path / "example.jar"
    calls = {}

    monkeypatch.setattr(
        "src.core.curseforge.curseforge_downloader.CurseForgeClient.get_download_url",
        staticmethod(lambda project_id, file_id, force_refresh=False: "https://cdn.example/example.jar"),
    )
    monkeypatch.setattr(
        "src.core.curseforge.curseforge_downloader.CurseForgeDownloadFallback.find_exact_hash_mirror",
        staticmethod(lambda *args, **kwargs: None),
    )

    def fake_download(request, **kwargs):
        calls["url"] = request.direct_url
        calls["target"] = request.destination
        return DownloadResult(request.destination, request.expected_size, request.hashes, source_url=request.direct_url)

    monkeypatch.setattr("src.core.curseforge.curseforge_downloader.artifact_download_service.download", fake_download)

    result = CurseForgeDownloader.download_file(make_file(download_url=""), destination)

    assert result == destination
    assert calls == {"url": "https://cdn.example/example.jar", "target": destination}


def test_forbidden_download_url_endpoint_uses_manual_fallback(monkeypatch, tmp_path: Path) -> None:
    error = RuntimeError("CurseForge returned HTTP 403.")
    setattr(error, "gateway_status", 403)

    def fail(*_args, **_kwargs):
        raise error

    monkeypatch.setattr("src.core.curseforge.curseforge_downloader.CurseForgeClient.get_download_url", staticmethod(fail))
    monkeypatch.setattr(
        "src.core.curseforge.curseforge_downloader.CurseForgeDownloadFallback.find_exact_hash_mirror",
        staticmethod(lambda *args, **kwargs: None),
    )

    with pytest.raises(CurseForgeManualDownloadRequired):
        CurseForgeDownloader.download_file(make_file(download_url="", is_available=True), tmp_path / "example.jar")


def test_gateway_failure_uses_exact_modrinth_sha1_mirror(monkeypatch, tmp_path: Path) -> None:
    gateway_error = RuntimeError("The CurseForge gateway credentials are unavailable.")
    setattr(gateway_error, "gateway_error_code", "CURSEFORGE_CREDENTIALS_UNAVAILABLE")
    monkeypatch.setattr(
        "src.core.curseforge.curseforge_downloader.CurseForgeClient.get_download_url",
        staticmethod(lambda *args, **kwargs: (_ for _ in ()).throw(gateway_error)),
    )
    monkeypatch.setattr(
        "src.core.curseforge.curseforge_downloader.CurseForgeDownloadFallback.find_exact_hash_mirror",
        staticmethod(lambda *args, **kwargs: SimpleNamespace(url="https://cdn.modrinth.com/example.jar", file_name="mirror.jar", size=10)),
    )
    captured = {}

    def fake_download(request, **kwargs):
        captured["url"] = request.direct_url
        captured["sha1"] = request.hashes["sha1"]
        captured["destination"] = request.destination
        return DownloadResult(request.destination, request.expected_size, request.hashes, source_url=request.direct_url)

    monkeypatch.setattr("src.core.curseforge.curseforge_downloader.artifact_download_service.download", fake_download)
    destination = tmp_path / "example.jar"

    result = CurseForgeDownloader.download_file(make_file(download_url=""), destination)

    assert result == destination
    assert captured == {
        "url": "https://cdn.modrinth.com/example.jar",
        "sha1": "a" * 40,
        "destination": destination,
    }


def test_project_url_resolution_replaces_numeric_placeholder(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.core.curseforge.curseforge_downloader.CurseForgeClient.get_project",
        staticmethod(lambda project_id: SimpleNamespace(project_url="https://www.curseforge.com/minecraft/mc-mods/example-mod")),
    )

    resolved = CurseForgeDownloader._resolve_project_url(1234, "https://www.curseforge.com/minecraft/mc-mods/1234")

    assert resolved == "https://www.curseforge.com/minecraft/mc-mods/example-mod"


def test_project_url_resolution_uses_search_page_when_metadata_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.core.curseforge.curseforge_downloader.CurseForgeClient.get_project",
        staticmethod(lambda project_id: (_ for _ in ()).throw(RuntimeError("offline"))),
    )

    resolved = CurseForgeDownloader._resolve_project_url(1234)

    assert resolved == "https://www.curseforge.com/minecraft/search?search=1234"
