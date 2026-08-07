from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile
import hashlib


from src.core.modloader.forge.legacy_libloader_manager import LegacyLibLoaderManager
from src.models.instance.instance import Instance


class _FakeDownloadService:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.requests = []

    def download(self, request, **_kwargs):
        self.requests.append(request)
        request.destination.parent.mkdir(parents=True, exist_ok=True)
        request.destination.write_bytes(self.payload)
        return request.destination


def _instance(tmp_path: Path, loader: str = "forge") -> Instance:
    root = tmp_path / "instance"
    (root / "mods").mkdir(parents=True)
    return Instance(instance_id="instance-id", name="RLCraft", version_id="1.12.2", instance_dir=root, mod_loader=(loader, "14.23.5.2860"))


def _write_manifest_jar(path: Path, attributes: dict[str, str], embedded: dict[str, bytes] | None = None) -> None:
    lines = ["Manifest-Version: 1.0", *(f"{key}: {value}" for key, value in attributes.items()), "", ""]
    with ZipFile(path, "w") as archive:
        archive.writestr("META-INF/MANIFEST.MF", "\r\n".join(lines))
        for name, payload in (embedded or {}).items():
            archive.writestr(name, payload)


def test_recovers_jcenter_only_library_from_verified_fallback(tmp_path: Path) -> None:
    instance = _instance(tmp_path)
    payload = b"verified WhoCalled library"
    sha512 = hashlib.sha512(payload).hexdigest()
    _write_manifest_jar(
        instance.instance_dir / "mods" / "# LibLoader.jar",
        {
            "LibLoader-group0": "me.nallar.whocalled",
            "LibLoader-name0": "WhoCalled",
            "LibLoader-version0": "1.1",
            "LibLoader-sha512hash0": sha512,
            "LibLoader-url0": "https://jcenter.bintray.com/me/nallar/whocalled/WhoCalled/1.1/WhoCalled-1.1.jar",
            "LibLoader-buildTime0": "1",
        },
    )
    service = _FakeDownloadService(payload)

    warnings = LegacyLibLoaderManager.ensure(instance, service=service)

    destination = instance.instance_dir / "libraries" / "me" / "nallar" / "whocalled" / "WhoCalled-1.1" / "WhoCalled-1.1.jar"
    assert destination.read_bytes() == payload
    assert len(warnings) == 1
    assert "1" in warnings[0]
    assert len(service.requests) == 1
    request = service.requests[0]
    assert request.hashes == {"sha512": sha512}
    assert request.urls[0].startswith("https://jcenter.bintray.com/")
    assert "https://repo1.maven.org/maven2/me/nallar/whocalled/WhoCalled/1.1/WhoCalled-1.1.jar" in request.urls
    assert request.urls[-1].endswith("/me.nallar.whocalled.WhoCalled-1.1.jar")


def test_verified_cached_library_skips_network(tmp_path: Path) -> None:
    instance = _instance(tmp_path)
    payload = b"cached"
    sha512 = hashlib.sha512(payload).hexdigest()
    _write_manifest_jar(
        instance.instance_dir / "mods" / "# LibLoader.jar",
        {
            "LibLoader-group0": "me.nallar.whocalled",
            "LibLoader-name0": "WhoCalled",
            "LibLoader-version0": "1.1",
            "LibLoader-sha512hash0": sha512,
            "LibLoader-url0": "https://jcenter.bintray.com/me/nallar/whocalled/WhoCalled/1.1/WhoCalled-1.1.jar",
        },
    )
    destination = instance.instance_dir / "libraries" / "me" / "nallar" / "whocalled" / "WhoCalled-1.1" / "WhoCalled-1.1.jar"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(payload)
    service = _FakeDownloadService(payload)

    assert LegacyLibLoaderManager.ensure(instance, service=service) == ()
    assert service.requests == []


def test_extracts_embedded_dependency_and_uses_snapshot_hash_directory(tmp_path: Path) -> None:
    instance = _instance(tmp_path)
    payload = b"embedded dependency"
    sha512 = hashlib.sha512(payload).hexdigest()
    _write_manifest_jar(
        instance.instance_dir / "mods" / "provider.jar",
        {
            "LibLoader-group0": "org.example",
            "LibLoader-name0": "demo",
            "LibLoader-version0": "1.0-SNAPSHOT",
            "LibLoader-sha512hash0": sha512,
            "LibLoader-file0": "META-INF/libs/demo.jar",
            "LibLoader-buildTime0": "9",
        },
        {"META-INF/libs/demo.jar": payload},
    )

    LegacyLibLoaderManager.ensure(instance, service=_FakeDownloadService(b"unused"))

    destination = instance.instance_dir / "libraries" / "org" / "example" / f"demo-1.0-SNAPSHOT-{sha512[:16]}" / "demo-1.0-SNAPSHOT.jar"
    assert destination.read_bytes() == payload


def test_non_forge_instance_is_ignored(tmp_path: Path) -> None:
    instance = _instance(tmp_path, loader="fabric")
    assert LegacyLibLoaderManager.ensure(instance, service=_FakeDownloadService(b"unused")) == ()


def test_unknown_remote_host_is_left_to_the_mod_instead_of_blocking_launch(tmp_path: Path) -> None:
    instance = _instance(tmp_path)
    payload = b"unknown"
    sha512 = hashlib.sha512(payload).hexdigest()
    _write_manifest_jar(
        instance.instance_dir / "mods" / "# LibLoader.jar",
        {
            "LibLoader-group0": "org.example",
            "LibLoader-name0": "unknown",
            "LibLoader-version0": "1.0",
            "LibLoader-sha512hash0": sha512,
            "LibLoader-url0": "https://example.invalid/unknown.jar",
        },
    )

    service = _FakeDownloadService(payload)
    assert LegacyLibLoaderManager.ensure(instance, service=service) == ()
    assert service.requests == []


def test_maven2_prefix_is_not_duplicated_in_fallback_urls(tmp_path: Path) -> None:
    instance = _instance(tmp_path)
    payload = b"maven path"
    sha512 = hashlib.sha512(payload).hexdigest()
    _write_manifest_jar(
        instance.instance_dir / "mods" / "# LibLoader.jar",
        {
            "LibLoader-group0": "me.nallar.whocalled",
            "LibLoader-name0": "WhoCalled",
            "LibLoader-version0": "1.1",
            "LibLoader-sha512hash0": sha512,
            "LibLoader-url0": "https://repo1.maven.org/maven2/me/nallar/whocalled/WhoCalled/1.1/WhoCalled-1.1.jar",
        },
    )
    service = _FakeDownloadService(payload)

    LegacyLibLoaderManager.ensure(instance, service=service)

    urls = service.requests[0].urls
    assert "https://repo1.maven.org/maven2/me/nallar/whocalled/WhoCalled/1.1/WhoCalled-1.1.jar" in urls
    assert not any("/maven2/maven2/" in url for url in urls)
