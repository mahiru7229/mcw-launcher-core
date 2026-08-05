from pathlib import Path

from src.core.update.github_release_client import GitHubReleaseClient


def release(tag: str, prerelease: bool, assets: list[dict], draft: bool = False) -> dict:
    return {
        "tag_name": tag,
        "name": tag,
        "body": "notes",
        "html_url": f"https://github.com/example/repo/releases/tag/{tag}",
        "published_at": "2026-07-15T00:00:00Z",
        "prerelease": prerelease,
        "draft": draft,
        "assets": assets,
    }


def asset(name: str, size: int = 123, digest: str | None = None) -> dict:
    return {
        "name": name,
        "size": size,
        "digest": digest,
        "browser_download_url": f"https://github.com/example/repo/releases/download/v/{name}",
    }


def test_selects_newest_beta_release_and_best_windows_zip(tmp_path: Path) -> None:
    client = GitHubReleaseClient("example/repo", "0.5.0-beta.2", "beta", tmp_path / "cache.json")
    update = client._select_update([
        release("v0.5.0-beta.3", True, [asset("random.zip"), asset("MCW-Launcher-v0.5.0-beta.3-windows-x64.zip", digest="sha256:" + "a" * 64)]),
        release("v0.5.0-beta.4", True, [asset("notes.txt")]),
        release("v0.5.0-beta.2", True, [asset("MCW.zip")]),
    ])

    assert update is not None
    assert update.version == "0.5.0-beta.3"
    assert update.asset.name == "MCW-Launcher-v0.5.0-beta.3-windows-x64.zip"
    assert update.asset.sha256 == "a" * 64


def test_stable_channel_ignores_prereleases(tmp_path: Path) -> None:
    client = GitHubReleaseClient("example/repo", "0.5.0-beta.2", "stable", tmp_path / "cache.json")
    update = client._select_update([
        release("v0.5.0-beta.4", True, [asset("MCW-windows-x64.zip")]),
        release("v0.5.0", False, [asset("MCW-windows-x64.zip")]),
    ])

    assert update is not None
    assert update.version == "0.5.0"


def test_drafts_and_releases_without_zip_are_ignored(tmp_path: Path) -> None:
    client = GitHubReleaseClient("example/repo", "0.5.0-beta.2", "beta", tmp_path / "cache.json")
    update = client._select_update([
        release("v0.5.0-beta.4", True, [asset("MCW.exe")]),
        release("v0.5.0-beta.3", True, [asset("MCW.zip")], draft=True),
    ])

    assert update is None


def test_beta_channel_does_not_upgrade_to_alpha_release(tmp_path: Path) -> None:
    client = GitHubReleaseClient("example/repo", "0.5.0-beta.2", "beta", tmp_path / "cache.json")
    update = client._select_update([
        release("v0.6.0-alpha.1", True, [asset("MCW-windows-x64.zip")]),
        release("v0.5.0-beta.3", True, [asset("MCW-windows-x64.zip")]),
    ])

    assert update is not None
    assert update.version == "0.5.0-beta.3"
