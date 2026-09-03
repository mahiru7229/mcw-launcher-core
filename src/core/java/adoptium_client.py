from __future__ import annotations

from pathlib import PurePosixPath
import re
from typing import Any
from urllib.parse import unquote, urlparse

from src.core.network.httpx_downloader import HttpDownloader
from src.core.system.platform_info import PlatformInfo, PlatformProfile
from src.models.java.java_release import JavaRelease


class AdoptiumClient:
    ASSETS_URL = "https://api.adoptium.net/v3/assets/latest/{major}/hotspot"
    AVAILABLE_RELEASES_URL = "https://api.adoptium.net/v3/info/available_releases"
    BASE_ASSETS_PARAMS = {
        "heap_size": "normal",
        "image_type": "jdk",
        "jvm_impl": "hotspot",
        "project": "jdk",
        "vendor": "eclipse",
    }

    @staticmethod
    def get_latest_jdk(
        major: int,
        timeout: float = 30.0,
        profile: PlatformProfile | None = None,
    ) -> JavaRelease:
        managed_major = AdoptiumClient.normalize_feature_major(major)
        selected_profile = profile or PlatformInfo.current()
        if selected_profile.os_name not in {"windows", "linux"}:
            raise RuntimeError(
                f"Managed Java is not supported on {selected_profile.os_name or 'this platform'}."
            )

        params = {
            **AdoptiumClient.BASE_ASSETS_PARAMS,
            "architecture": selected_profile.adoptium_architecture,
            "os": selected_profile.os_name,
        }
        api_url = AdoptiumClient.ASSETS_URL.format(major=managed_major)
        response = HttpDownloader.get_client().get(api_url, params=params, timeout=timeout)
        response.raise_for_status()

        try:
            payload = response.json()
        except ValueError as error:
            raise RuntimeError(f"Invalid Adoptium metadata response for Java {managed_major}.") from error

        asset, package = AdoptiumClient._select_package(payload, managed_major, selected_profile)
        download_url = AdoptiumClient._required_string(package.get("link"), "download URL", managed_major)
        sha256 = AdoptiumClient._parse_sha256(package.get("checksum"), managed_major)
        filename = AdoptiumClient._package_filename(
            package.get("name"),
            download_url,
            managed_major,
            selected_profile.archive_suffix,
        )
        size = AdoptiumClient._content_length(package.get("size"))
        release_name = AdoptiumClient._release_name(asset.get("release_name"), filename)
        return JavaRelease(
            major=managed_major,
            url=download_url,
            sha256=sha256,
            size=size,
            filename=filename,
            release_name=release_name,
        )

    @staticmethod
    def get_latest_windows_x64_jdk(major: int, timeout: float = 30.0) -> JavaRelease:
        """Compatibility wrapper for consumers of the pre-Alpha-2 API."""
        from src.core.system.platform_info import PlatformProfile

        return AdoptiumClient.get_latest_jdk(
            major,
            timeout,
            PlatformProfile(
                os_name="windows",
                architecture="x64",
                adoptium_architecture="x64",
                java_executable="javaw.exe",
                java_console_executable="java.exe",
                archive_suffix=".zip",
            ),
        )

    @staticmethod
    def get_latest_feature_release(timeout: float = 15.0) -> int:
        response = HttpDownloader.get_client().get(AdoptiumClient.AVAILABLE_RELEASES_URL, timeout=timeout)
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as error:
            raise RuntimeError("Invalid Adoptium available-releases response.") from error
        return AdoptiumClient._parse_latest_feature_release(payload)

    @staticmethod
    def _parse_latest_feature_release(payload: Any) -> int:
        if not isinstance(payload, dict):
            raise RuntimeError("Adoptium available-releases response must be an object.")
        direct = payload.get("most_recent_feature_release")
        if direct is not None:
            return AdoptiumClient.normalize_feature_major(direct)
        available = payload.get("available_releases")
        if isinstance(available, list):
            majors: list[int] = []
            for value in available:
                try:
                    majors.append(AdoptiumClient.normalize_feature_major(value))
                except RuntimeError:
                    continue
            if majors:
                return max(majors)
        raise RuntimeError("Adoptium did not report a latest GA Java feature release.")

    @staticmethod
    def normalize_feature_major(value: Any) -> int:
        try:
            major = int(value)
        except (TypeError, ValueError) as error:
            raise RuntimeError(f"Invalid Java feature version: {value!r}.") from error
        if major < 8 or major > 99:
            raise RuntimeError(f"Unsupported Java feature version: {major}.")
        return major

    @staticmethod
    def _select_package(
        payload: Any,
        major: int,
        profile: PlatformProfile | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        selected_profile = profile or PlatformInfo.current()
        assets = payload if isinstance(payload, list) else [payload]
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            for binary in AdoptiumClient._iter_binaries(asset):
                if not AdoptiumClient._matches_platform(binary, selected_profile):
                    continue
                package = binary.get("package")
                if not isinstance(package, dict):
                    continue
                link = package.get("link")
                if isinstance(link, str) and AdoptiumClient._has_archive_suffix(
                    link.split("?", 1)[0], selected_profile.archive_suffix
                ):
                    return asset, package
        platform_label = f"{selected_profile.os_name} {selected_profile.adoptium_architecture}"
        raise RuntimeError(
            f"Adoptium did not return a {platform_label} JDK {selected_profile.archive_suffix} package "
            f"for Java {major}."
        )

    @staticmethod
    def _iter_binaries(asset: dict[str, Any]) -> list[dict[str, Any]]:
        binaries: list[dict[str, Any]] = []
        binary = asset.get("binary")
        if isinstance(binary, dict):
            binaries.append(binary)
        legacy_binaries = asset.get("binaries")
        if isinstance(legacy_binaries, list):
            binaries.extend(item for item in legacy_binaries if isinstance(item, dict))
        return binaries

    @staticmethod
    def _matches_platform(binary: dict[str, Any], profile: PlatformProfile) -> bool:
        expected_values = {
            "architecture": profile.adoptium_architecture,
            "image_type": "jdk",
            "jvm_impl": "hotspot",
            "os": profile.os_name,
        }
        return all(
            binary.get(key) is None or str(binary.get(key)).casefold() == expected.casefold()
            for key, expected in expected_values.items()
        )

    @staticmethod
    def _parse_sha256(content: Any, major: int) -> str:
        if not isinstance(content, str):
            raise RuntimeError(f"Adoptium metadata is missing the SHA-256 checksum for Java {major}.")
        match = re.search(r"\b[0-9a-fA-F]{64}\b", content)
        if match is None:
            raise RuntimeError(f"Invalid Adoptium SHA-256 checksum for Java {major}.")
        return match.group(0).lower()

    @staticmethod
    def _package_filename(
        raw_name: Any,
        url: str,
        major: int,
        archive_suffix: str = ".zip",
    ) -> str:
        filename = raw_name.strip() if isinstance(raw_name, str) and raw_name.strip() else unquote(
            PurePosixPath(urlparse(url).path).name
        )
        if not AdoptiumClient._has_archive_suffix(filename, archive_suffix):
            raise RuntimeError(
                f"Adoptium did not return a {archive_suffix} package for Java {major}."
            )
        if "/" in filename or "\\" in filename or filename in {".", ".."}:
            raise RuntimeError(f"Adoptium returned an unsafe package name for Java {major}.")
        return filename

    @staticmethod
    def _has_archive_suffix(value: str, suffix: str) -> bool:
        return str(value).casefold().endswith(str(suffix).casefold())

    @staticmethod
    def _required_string(value: Any, field_name: str, major: int) -> str:
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(f"Adoptium metadata is missing the {field_name} for Java {major}.")
        return value.strip()

    @staticmethod
    def _release_name(raw_name: Any, filename: str) -> str:
        if isinstance(raw_name, str) and raw_name.strip():
            return raw_name.strip()
        for suffix in (".tar.gz", ".zip"):
            if filename.casefold().endswith(suffix):
                return filename[: -len(suffix)]
        return filename

    @staticmethod
    def _content_length(raw_length: Any) -> int:
        try:
            return max(0, int(raw_length))
        except (TypeError, ValueError):
            return 0
