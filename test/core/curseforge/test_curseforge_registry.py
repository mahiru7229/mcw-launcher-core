from pathlib import Path

from src.core.curseforge.curseforge_pack_registry import CurseForgePackRegistry
from src.core.curseforge.curseforge_registry import CurseForgeRegistry


def test_pack_registry_preserves_retry_state_and_normalizes_path() -> None:
    data = CurseForgePackRegistry._normalize({
        "managedFiles": [{
            "projectId": 1,
            "fileId": 2,
            "fileName": "example.jar",
            "path": "../outside.jar",
            "pendingDownload": True,
            "lastDownloadError": "network error",
        }]
    })

    entry = data["managedFiles"][0]
    assert entry["path"] == "mods/example.jar"
    assert entry["pendingDownload"] is True
    assert entry["lastDownloadError"] == "network error"


def test_mod_registry_drops_invalid_entries() -> None:
    data = CurseForgeRegistry._normalize({
        "mods": {
            "1": {"projectId": 1, "fileId": 2, "fileName": "example.jar"},
            "invalid": {"projectId": "x", "fileId": 0},
        }
    })

    assert list(data["mods"]) == ["1"]
    assert data["mods"]["1"]["source"] == "curseforge"
