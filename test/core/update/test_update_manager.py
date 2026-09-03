from pathlib import Path
import os
import zipfile

import pytest

from src.core.update.update_manager import UpdateManager


def make_zip(path: Path, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)


def manager() -> UpdateManager:
    return UpdateManager("example/repo", "0.5.0-beta.2", platform_id="windows-x64")


def test_extracts_release_zip_and_flattens_single_root_directory(tmp_path: Path) -> None:
    archive_path = tmp_path / "release.zip"
    extraction = tmp_path / "extracted"
    extraction.mkdir()
    make_zip(archive_path, {
        "MCW-Launcher/MCW Launcher.exe": b"exe",
        "MCW-Launcher/lang/en-US.json": b"{}",
    })

    manager()._extract_archive(archive_path, extraction)
    content = manager()._resolve_content_directory(extraction)

    assert content == extraction / "MCW-Launcher"
    assert (content / "MCW Launcher.exe").read_bytes() == b"exe"
    assert (content / "lang" / "en-US.json").read_bytes() == b"{}"


def test_extracts_zip_with_files_at_root_without_flattening(tmp_path: Path) -> None:
    archive_path = tmp_path / "release.zip"
    extraction = tmp_path / "extracted"
    extraction.mkdir()
    make_zip(archive_path, {"MCW Launcher.exe": b"exe", "lang/en-US.json": b"{}"})

    manager()._extract_archive(archive_path, extraction)

    assert manager()._resolve_content_directory(extraction) == extraction


@pytest.mark.parametrize("name", ["../evil.exe", "/absolute.exe", "C:/evil.exe", "folder/../../evil.exe", "..\\evil.exe"])
def test_rejects_unsafe_archive_paths(tmp_path: Path, name: str) -> None:
    archive_path = tmp_path / "release.zip"
    extraction = tmp_path / "extracted"
    extraction.mkdir()
    make_zip(archive_path, {name: b"bad"})

    with pytest.raises(RuntimeError, match="Unsafe path"):
        manager()._extract_archive(archive_path, extraction)


def test_validates_matching_update_package_manifest(tmp_path: Path) -> None:
    content = tmp_path / "content"
    content.mkdir()
    (content / "MCW Launcher.exe").write_bytes(b"exe")
    (content / "mcw-update.json").write_text('{"schema_version": 1, "version": "0.5.0-beta.3", "platform": "windows-x64", "executable": "MCW Launcher.exe", "files": ["MCW Launcher.exe", "mcw-update.json"]}', encoding="utf-8")
    from src.models.update.update_info import ReleaseAsset, UpdateInfo

    info = UpdateInfo(current_version="0.5.0-beta.2", version="0.5.0-beta.3", tag_name="v0.5.0-beta.3", title="Beta 3", release_notes="", release_url="", published_at="", prerelease=True, asset=ReleaseAsset("update.zip", "https://example.com/update.zip", 1))

    manager()._validate_package_manifest(content, info)


def test_rejects_update_package_version_mismatch(tmp_path: Path) -> None:
    content = tmp_path / "content"
    content.mkdir()
    (content / "MCW Launcher.exe").write_bytes(b"exe")
    (content / "mcw-update.json").write_text('{"schema_version": 1, "version": "0.5.0-beta.4", "platform": "windows-x64", "executable": "MCW Launcher.exe", "files": ["MCW Launcher.exe", "mcw-update.json"]}', encoding="utf-8")
    from src.models.update.update_info import ReleaseAsset, UpdateInfo

    info = UpdateInfo(current_version="0.5.0-beta.2", version="0.5.0-beta.3", tag_name="v0.5.0-beta.3", title="Beta 3", release_notes="", release_url="", published_at="", prerelease=True, asset=ReleaseAsset("update.zip", "https://example.com/update.zip", 1))

    with pytest.raises(RuntimeError, match="version mismatch"):
        manager()._validate_package_manifest(content, info)


def test_update_download_reports_progress(tmp_path: Path, monkeypatch) -> None:
    import hashlib
    import httpx

    from src.core.network.httpx_downloader import HttpDownloader
    from src.core.progress.progress_reporter import ProgressReporter
    from src.models.progress.progress_stage import ProgressStage
    from src.models.update.update_info import ReleaseAsset, UpdateInfo

    content = b"launcher-update-archive"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Length": str(len(content))}, content=content)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    monkeypatch.setattr(HttpDownloader, "_client", client)
    info = UpdateInfo(current_version="0.5.0-beta.9", version="0.5.0-beta.10", tag_name="v0.5.0-beta.10", title="Beta 10", release_notes="", release_url="", published_at="", prerelease=True, asset=ReleaseAsset("update.zip", "https://example.com/update.zip", len(content), hashlib.sha256(content).hexdigest()))
    events = []
    archive_path = tmp_path / "update.zip"

    manager()._download_archive(info, archive_path, ProgressReporter(events.append), max_retry=1)

    assert archive_path.read_bytes() == content
    assert events
    assert all(event.stage is ProgressStage.DOWNLOADING_UPDATE for event in events)
    assert events[-1].percentage == 100


def test_update_download_uses_shared_bandwidth_limiter(tmp_path: Path, monkeypatch) -> None:
    import hashlib
    import httpx

    from src.core.network.httpx_downloader import HttpDownloader
    from src.models.update.update_info import ReleaseAsset, UpdateInfo

    content = b"limited-launcher-update"
    throttled = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Length": str(len(content))}, content=content)

    monkeypatch.setattr(HttpDownloader, "_client", httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True))
    monkeypatch.setattr("src.core.update.update_manager.download_bandwidth_limiter.throttle", lambda size: throttled.append(size))
    info = UpdateInfo(current_version="0.5.1-beta.1", version="0.5.1-beta.2", tag_name="v0.5.1-beta.2", title="Beta 2", release_notes="", release_url="", published_at="", prerelease=True, asset=ReleaseAsset("update.zip", "https://example.com/update.zip", len(content), hashlib.sha256(content).hexdigest()))

    archive_path = tmp_path / "update.zip"
    manager()._download_archive(info, archive_path, max_retry=1)

    assert archive_path.read_bytes() == content
    assert sum(throttled) == len(content)


def test_rejects_update_package_without_manifest(tmp_path: Path) -> None:
    content = tmp_path / "content"
    content.mkdir()
    (content / "MCW Launcher.exe").write_bytes(b"exe")
    from src.models.update.update_info import ReleaseAsset, UpdateInfo

    info = UpdateInfo(current_version="0.5.0-beta.2", version="0.5.0-beta.3", tag_name="v0.5.0-beta.3", title="Beta 3", release_notes="", release_url="", published_at="", prerelease=True, asset=ReleaseAsset("update.zip", "https://example.com/update.zip", 1))

    with pytest.raises(RuntimeError, match="missing mcw-update.json"):
        manager()._validate_package_manifest(content, info)


def test_update_download_uses_sha256_sidecar_when_digest_missing(tmp_path: Path, monkeypatch) -> None:
    import hashlib
    import httpx

    from src.core.network.httpx_downloader import HttpDownloader
    from src.models.update.update_info import ReleaseAsset, UpdateInfo

    content = b"verified-by-sidecar"
    digest = hashlib.sha256(content).hexdigest()

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith(".sha256"):
            return httpx.Response(200, content=f"{digest}  update.zip\n".encode())
        return httpx.Response(200, headers={"Content-Length": str(len(content))}, content=content)

    monkeypatch.setattr(HttpDownloader, "_client", httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True))
    info = UpdateInfo(current_version="1.3.2", version="1.3.3", tag_name="v1.3.3", title="1.3.3", release_notes="", release_url="", published_at="", prerelease=False, asset=ReleaseAsset("update.zip", "https://example.com/update.zip", len(content), sha256_url="https://example.com/update.zip.sha256"))
    archive_path = tmp_path / "update.zip"

    manager()._download_archive(info, archive_path, max_retry=1)

    assert archive_path.read_bytes() == content


def test_update_download_refuses_unverified_archive(tmp_path: Path) -> None:
    from src.models.update.update_info import ReleaseAsset, UpdateInfo

    info = UpdateInfo(current_version="1.3.2", version="1.3.3", tag_name="v1.3.3", title="1.3.3", release_notes="", release_url="", published_at="", prerelease=False, asset=ReleaseAsset("update.zip", "https://example.com/update.zip", 123))

    with pytest.raises(RuntimeError, match="require a trusted SHA-256"):
        manager()._download_archive(info, tmp_path / "update.zip", max_retry=1)


@pytest.mark.skipif(os.name == "nt", reason="POSIX executable modes are validated by the Linux CI job")
def test_validates_linux_manifest_and_restores_executable_mode(tmp_path: Path) -> None:
    archive_path = tmp_path / "linux.zip"
    extraction = tmp_path / "extracted"
    extraction.mkdir()
    executable_info = zipfile.ZipInfo("MCW-Launcher/mcw-launcher")
    executable_info.create_system = 3
    executable_info.external_attr = (0o100755 << 16)
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(executable_info, b"linux-binary")
        archive.writestr(
            "MCW-Launcher/mcw-update.json",
            '{"schema_version": 1, "version": "0.5.0-beta.3", "platform": "linux-x64", "executable": "mcw-launcher", "files": ["mcw-launcher", "mcw-update.json"]}',
        )

    updater = UpdateManager("example/repo", "0.5.0-beta.2", platform_id="linux-x64")
    updater._extract_archive(archive_path, extraction)
    content = updater._resolve_content_directory(extraction)
    from src.models.update.update_info import ReleaseAsset, UpdateInfo

    info = UpdateInfo(current_version="0.5.0-beta.2", version="0.5.0-beta.3", tag_name="v0.5.0-beta.3", title="Beta 3", release_notes="", release_url="", published_at="", prerelease=True, asset=ReleaseAsset("linux.zip", "https://example.com/linux.zip", 1))
    updater._validate_package_manifest(content, info)

    assert (content / "mcw-launcher").stat().st_mode & 0o777 == 0o755


def test_rejects_update_package_for_another_platform(tmp_path: Path) -> None:
    content = tmp_path / "content"
    content.mkdir()
    executable = content / "mcw-launcher"
    executable.write_bytes(b"linux")
    executable.chmod(0o755)
    (content / "mcw-update.json").write_text(
        '{"schema_version": 1, "version": "0.5.0-beta.3", "platform": "windows-x64", "executable": "mcw-launcher", "files": ["mcw-launcher", "mcw-update.json"]}',
        encoding="utf-8",
    )
    from src.models.update.update_info import ReleaseAsset, UpdateInfo

    info = UpdateInfo(current_version="0.5.0-beta.2", version="0.5.0-beta.3", tag_name="v0.5.0-beta.3", title="Beta 3", release_notes="", release_url="", published_at="", prerelease=True, asset=ReleaseAsset("linux.zip", "https://example.com/linux.zip", 1))
    updater = UpdateManager("example/repo", "0.5.0-beta.2", platform_id="linux-x64")

    with pytest.raises(RuntimeError, match="platform mismatch"):
        updater._validate_package_manifest(content, info)


def test_rejects_symbolic_link_in_update_archive(tmp_path: Path) -> None:
    archive_path = tmp_path / "symlink.zip"
    extraction = tmp_path / "extracted"
    extraction.mkdir()
    link_info = zipfile.ZipInfo("MCW-Launcher/mcw-launcher")
    link_info.create_system = 3
    link_info.external_attr = (0o120777 << 16)
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(link_info, b"../../outside")

    with pytest.raises(RuntimeError, match="symbolic link"):
        UpdateManager("example/repo", "0.5.0-beta.2", platform_id="linux-x64")._extract_archive(
            archive_path,
            extraction,
        )


def test_rejects_undeclared_update_package_file(tmp_path: Path) -> None:
    content = tmp_path / "content"
    content.mkdir()
    executable = content / "mcw-launcher"
    executable.write_bytes(b"linux")
    executable.chmod(0o755)
    (content / "unexpected.sh").write_text("malicious", encoding="utf-8")
    (content / "mcw-update.json").write_text(
        '{"schema_version": 1, "version": "0.5.0-beta.3", "platform": "linux-x64", "executable": "mcw-launcher", "files": ["mcw-launcher", "mcw-update.json"]}',
        encoding="utf-8",
    )
    from src.models.update.update_info import ReleaseAsset, UpdateInfo

    info = UpdateInfo(current_version="0.5.0-beta.2", version="0.5.0-beta.3", tag_name="v0.5.0-beta.3", title="Beta 3", release_notes="", release_url="", published_at="", prerelease=True, asset=ReleaseAsset("linux.zip", "https://example.com/linux.zip", 1))

    with pytest.raises(RuntimeError, match="undeclared file"):
        UpdateManager("example/repo", "0.5.0-beta.2", platform_id="linux-x64")._validate_package_manifest(content, info)


def test_rejects_duplicate_archive_paths_case_insensitively(tmp_path: Path) -> None:
    archive_path = tmp_path / "duplicate.zip"
    extraction = tmp_path / "extracted"
    extraction.mkdir()
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("MCW-Launcher/lang/en-US.json", b"one")
        archive.writestr("mcw-launcher/lang/en-us.json", b"two")

    with pytest.raises(RuntimeError, match="duplicate path"):
        manager()._extract_archive(archive_path, extraction)
