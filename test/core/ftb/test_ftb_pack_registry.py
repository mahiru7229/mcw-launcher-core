from pathlib import Path

from src.core.ftb.ftb_pack_registry import FTBPackRegistry


def test_registry_round_trip_normalizes_paths_and_files(tmp_path: Path) -> None:
    FTBPackRegistry.save(tmp_path, {
        "projectId": 25,
        "versionId": 101,
        "managedFiles": [
            {
                "fileId": 2,
                "fileName": "b.jar",
                "path": "mods/b.jar",
                "sha1": "A" * 40,
                "size": 2,
                "urls": ["https://one.example/b.jar", "https://one.example/b.jar"],
            },
            {
                "fileId": 1,
                "fileName": "a.jar",
                "path": "../a.jar",
                "sha1": "B" * 40,
                "size": 1,
            },
        ],
    })

    data = FTBPackRegistry.load(tmp_path)

    assert data["schemaVersion"] == 2
    assert data["source"] == "ftb"
    assert [entry["fileName"] for entry in data["managedFiles"]] == ["a.jar", "b.jar"]
    assert data["managedFiles"][0]["path"] == "a.jar"
    assert data["managedFiles"][1]["urls"] == ["https://one.example/b.jar"]
    assert data["managedFiles"][1]["sha1"] == "a" * 40
    assert data["managedFiles"][1]["provider"] == "ftb"
