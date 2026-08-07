from pathlib import Path
import json

from src.core.fs.paths import Paths
from src.core.optifine.optifine_metadata_client import OptiFineMetadataClient


def test_client_uses_stale_cache_when_network_fails(tmp_path: Path, monkeypatch) -> None:
    previous = Paths.configure(tmp_path)
    try:
        cache = Paths.optifine_metadata_cache()
        cache.parent.mkdir(parents=True)
        cache.write_text(json.dumps({
            "fetchedAtEpoch": 0,
            "versions": [{
                "minecraft_version": "1.12.2", "edition": "HD_U", "build": "G5",
                "filename": "OptiFine_1.12.2_HD_U_G5.jar", "preview": False,
                "forge_version": "", "release_date": "", "download_page_url": "https://optifine.net/downloads",
                "mirror_url": "", "changelog_url": ""
            }]
        }), encoding="utf-8")
        class Broken:
            def get(self, *args, **kwargs):
                raise OSError("offline")
        monkeypatch.setattr("src.core.optifine.optifine_metadata_client.HttpDownloader.get_client", lambda: Broken())
        versions = OptiFineMetadataClient.list_versions("1.12.2")
        assert [item.build for item in versions] == ["G5"]
    finally:
        Paths.restore(previous)
