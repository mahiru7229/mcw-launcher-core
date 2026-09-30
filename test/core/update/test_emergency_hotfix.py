from pathlib import Path

from src.core.update.github_release_client import GitHubReleaseClient


def release(tag: str, prerelease: bool, assets: list[dict], draft: bool = False) -> dict:
    return {
        "tag_name": tag,
        "name": tag,
        "body": "notes",
        "html_url": f"https://github.com/example/repo/releases/tag/{tag}",
        "published_at": "2026-09-13T00:00:00Z",
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


def test_alpha_version_can_update_to_newer_alpha(tmp_path: Path) -> None:
    client = GitHubReleaseClient("example/repo", "1.6.0-alpha.2", "beta", tmp_path / "cache.json")
    update = client._select_update([
        release("v1.6.0-alpha.3", True, [asset("MCW-Launcher-v1.6.0-alpha.3-windows-x64.zip")]),
    ])
    assert update is not None
    assert update.version == "1.6.0-alpha.3"
    assert not update.emergency


def test_beta_user_ignores_alpha_release(tmp_path: Path) -> None:
    client = GitHubReleaseClient("example/repo", "1.5.1-beta.6", "beta", tmp_path / "cache.json")
    update = client._select_update([
        release("v1.6.0-alpha.1", True, [asset("MCW-Launcher-v1.6.0-alpha.1-windows-x64.zip")]),
    ])
    assert update is None


def test_emergency_hotfix_marker_allows_downgrade(tmp_path: Path) -> None:
    client = GitHubReleaseClient("example/repo", "1.6.0-alpha.2", "beta", tmp_path / "cache.json")
    update = client._select_update([
        release("v1.5.1", False, [
            asset("MCW-Launcher-v1.5.1-windows-x64.zip"),
            asset("MCW-EMERGENCY-HOTFIX", size=0),
        ]),
    ])
    assert update is not None
    assert update.version == "1.5.1"
    assert update.emergency is True


def test_emergency_marker_takes_precedence_over_higher_version(tmp_path: Path) -> None:
    client = GitHubReleaseClient("example/repo", "1.6.0-alpha.2", "beta", tmp_path / "cache.json")
    update = client._select_update([
        release("v1.6.0-alpha.3", True, [asset("MCW-Launcher-v1.6.0-alpha.3-windows-x64.zip")]),
        release("v1.5.1", False, [
            asset("MCW-Launcher-v1.5.1-windows-x64.zip"),
            asset("MCW-EMERGENCY-HOTFIX", size=0),
        ]),
    ])
    assert update is not None
    assert update.version == "1.5.1"
    assert update.emergency is True
