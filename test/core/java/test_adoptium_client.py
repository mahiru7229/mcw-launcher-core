from src.core.java.adoptium_client import AdoptiumClient
from src.core.system.platform_info import PlatformProfile


WINDOWS_X64 = PlatformProfile("windows", "x64", "x64", "javaw.exe", "java.exe", ".zip")
LINUX_X64 = PlatformProfile("linux", "x64", "x64", "java", "java", ".tar.gz")


def test_selects_checksum_from_latest_assets_metadata():
    checksum = "a" * 64
    payload = [{
        "release_name": "jdk8u452-b09",
        "binary": {
            "architecture": "x64",
            "image_type": "jdk",
            "jvm_impl": "hotspot",
            "os": "windows",
            "package": {
                "checksum": checksum,
                "link": "https://example.test/OpenJDK8U-jdk_x64_windows_hotspot_8u452b09.zip",
                "name": "OpenJDK8U-jdk_x64_windows_hotspot_8u452b09.zip",
                "size": 123,
            },
        },
    }]

    asset, package = AdoptiumClient._select_package(payload, 8, WINDOWS_X64)

    assert asset["release_name"] == "jdk8u452-b09"
    assert AdoptiumClient._parse_sha256(package["checksum"], 8) == checksum


def test_supports_legacy_binaries_shape():
    payload = {
        "binaries": [{
            "architecture": "x64",
            "image_type": "jdk",
            "jvm_impl": "hotspot",
            "os": "windows",
            "package": {
                "checksum": "b" * 64,
                "link": "https://example.test/java-17.zip",
            },
        }],
    }

    _, package = AdoptiumClient._select_package(payload, 17, WINDOWS_X64)

    assert package["link"].endswith("java-17.zip")


def test_rejects_missing_checksum():
    try:
        AdoptiumClient._parse_sha256(None, 8)
    except RuntimeError as error:
        assert "missing" in str(error).lower()
    else:
        raise AssertionError("Missing checksum must be rejected")

def test_parses_latest_ga_feature_release_without_using_tip_version():
    payload = {
        "available_releases": [8, 11, 17, 21, 25, 26],
        "most_recent_feature_release": 26,
        "tip_version": 27,
    }

    assert AdoptiumClient._parse_latest_feature_release(payload) == 26


def test_falls_back_to_highest_available_release():
    assert AdoptiumClient._parse_latest_feature_release({"available_releases": [8, "17", 21, 26]}) == 26


def test_selects_linux_tar_gz_package():
    payload = [{
        "binary": {
            "architecture": "x64",
            "image_type": "jdk",
            "jvm_impl": "hotspot",
            "os": "linux",
            "package": {
                "checksum": "c" * 64,
                "link": "https://example.test/OpenJDK21U-jdk_x64_linux_hotspot.tar.gz",
            },
        }
    }]

    _, package = AdoptiumClient._select_package(payload, 21, LINUX_X64)

    assert package["link"].endswith(".tar.gz")
