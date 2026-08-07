from src.core.modrinth.modrinth_client import ModrinthClient


def test_get_version_from_hash_uses_version_file_endpoint(monkeypatch):
    seen = {}

    def fake_get(path, params=None, **_kwargs):
        seen["path"] = path
        seen["params"] = params
        return {"id": "version", "project_id": "project", "version_number": "1.0", "files": []}

    monkeypatch.setattr(ModrinthClient, "_get_json", fake_get)
    version = ModrinthClient.get_version_from_hash("A" * 128, "sha512")

    assert version is not None
    assert version.version_id == "version"
    assert seen == {"path": "/version_file/" + "a" * 128, "params": {"algorithm": "sha512"}}


def test_get_version_from_hash_returns_none_for_404(monkeypatch):
    monkeypatch.setattr(ModrinthClient, "_get_json", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("Modrinth API request failed with HTTP 404.")))
    assert ModrinthClient.get_version_from_hash("b" * 40, "sha1") is None
