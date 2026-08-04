from __future__ import annotations

from pathlib import Path
import hashlib
import json
import os
import shutil

from src.models.instance.instance import Instance


class ProviderPackageStore:
    DIRECTORY = "provider"
    ORIGIN_FILE = "origin.json"
    MAX_NATIVE_PACKAGE_BYTES = 8 * 1024 * 1024 * 1024

    @staticmethod
    def root(instance: Instance | Path) -> Path:
        instance_dir = Path(instance.instance_dir) if isinstance(instance, Instance) else Path(instance)
        return instance_dir / ".mcw" / ProviderPackageStore.DIRECTORY

    @staticmethod
    def origin_path(instance: Instance | Path) -> Path:
        return ProviderPackageStore.root(instance) / ProviderPackageStore.ORIGIN_FILE

    @staticmethod
    def load_origin(instance: Instance | Path) -> dict:
        try:
            data = json.loads(ProviderPackageStore.origin_path(instance).read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def save_origin(instance: Instance | Path, data: dict) -> None:
        root = ProviderPackageStore.root(instance)
        root.mkdir(parents=True, exist_ok=True)
        payload = ProviderPackageStore._normalize_origin(data)
        temporary = ProviderPackageStore.origin_path(instance).with_suffix(".json.part")
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(ProviderPackageStore.origin_path(instance))

    @staticmethod
    def store_native_package(instance: Instance | Path, source_path: Path, provider: str, package_format: str, origin: dict | None = None) -> Path:
        source = Path(source_path)
        if not source.is_file():
            raise RuntimeError("The provider package does not exist.")
        size = source.stat().st_size
        if size <= 0 or size > ProviderPackageStore.MAX_NATIVE_PACKAGE_BYTES:
            raise RuntimeError("The provider package is empty or exceeds the package safety limit.")
        suffix = ".mrpack" if str(package_format).casefold() == "mrpack" else ".zip"
        root = ProviderPackageStore.root(instance)
        root.mkdir(parents=True, exist_ok=True)
        target = root / f"original-package{suffix}"
        temporary = target.with_name(f".{target.name}.part")
        try:
            with source.open("rb") as input_stream, temporary.open("wb") as output_stream:
                shutil.copyfileobj(input_stream, output_stream, length=1024 * 1024)
                output_stream.flush()
                os.fsync(output_stream.fileno())
            temporary.replace(target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        data = dict(origin or {})
        data.update({
            "provider": str(provider or "").strip().casefold(),
            "packageFormat": str(package_format or "").strip().casefold(),
            "nativePackage": target.name,
            "nativePackageSha256": ProviderPackageStore.sha256(target),
            "nativePackageSize": target.stat().st_size,
            "nativePackageModified": False,
        })
        ProviderPackageStore.save_origin(instance, data)
        return target

    @staticmethod
    def native_package(instance: Instance | Path) -> Path | None:
        origin = ProviderPackageStore.load_origin(instance)
        name = Path(str(origin.get("nativePackage") or "")).name
        if name:
            candidate = ProviderPackageStore.root(instance) / name
            if candidate.is_file():
                expected = str(origin.get("nativePackageSha256") or "").strip().casefold()
                if not expected or ProviderPackageStore.sha256(candidate) == expected:
                    return candidate
        for candidate in sorted(ProviderPackageStore.root(instance).glob("original-package.*")):
            if candidate.is_file():
                return candidate
        return None

    @staticmethod
    def sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with Path(path).open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _normalize_origin(data: dict) -> dict:
        provider = str(data.get("provider") or "").strip().casefold()
        package_format = str(data.get("packageFormat") or "").strip().casefold()
        output = {
            "schemaVersion": 1,
            "provider": provider,
            "packageFormat": package_format,
            "projectId": str(data.get("projectId") or "").strip(),
            "versionId": str(data.get("versionId") or data.get("fileId") or "").strip(),
            "fileId": str(data.get("fileId") or "").strip(),
            "packName": str(data.get("packName") or "").strip(),
            "packVersion": str(data.get("packVersion") or "").strip(),
            "nativePackage": Path(str(data.get("nativePackage") or "")).name,
            "nativePackageSha256": str(data.get("nativePackageSha256") or "").strip().casefold(),
            "nativePackageSize": max(0, int(data.get("nativePackageSize", 0) or 0)),
            "nativePackageModified": bool(data.get("nativePackageModified", False)),
            "source": str(data.get("source") or "provider").strip().casefold() or "provider",
        }
        return output
