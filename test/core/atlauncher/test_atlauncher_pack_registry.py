from pathlib import Path

from src.core.atlauncher.atlauncher_pack_registry import ATLauncherPackRegistry


def test_registry_round_trip_normalizes_managed_files(tmp_path: Path) -> None:
    ATLauncherPackRegistry.save(tmp_path, {
        "packId": "25",
        "safeName": "ExamplePack",
        "versionId": "101",
        "versionName": "2.0.0",
        "managedFiles": [
            {
                "fileId": "b",
                "fileName": "b.jar",
                "path": "mods/b.jar",
                "md5": "A" * 32,
                "urls": ["https://one.example/b.jar", "https://one.example/b.jar"],
                "pendingDownload": True,
            },
            {"fileId": "bad", "fileName": "bad.jar", "path": "../bad.jar"},
        ],
    })

    data = ATLauncherPackRegistry.load(tmp_path)

    assert data["source"] == "atlauncher"
    assert data["safeName"] == "ExamplePack"
    assert len(data["managedFiles"]) == 1
    assert data["managedFiles"][0]["md5"] == "a" * 32
    assert data["managedFiles"][0]["urls"] == ["https://one.example/b.jar"]
    assert data["managedFiles"][0]["provider"] == "atlauncher"
