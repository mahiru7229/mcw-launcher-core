from src.models.minecraft.version import Version
from src.core.minecraft.version_manifest_manager import VersionManifestManager
from src.core.fs.paths import Paths
from pathlib import Path
import requests
import json
#dict_keys(
# ['arguments',
#  'assetIndex',
#  'assets',
#  'complianceLevel',
#  'downloads', 'id',
#  'javaVersion',
#  'libraries',
#  'logging',
#  'mainClass',
#  'minimumLauncherVersion',
#  'releaseTime',
#  'time',
#  'type'])




class VersionManager:
    @staticmethod
    def load(id:str=VersionManifestManager.latest_version()) -> Version:
        """
        Default: Loading newest version of Minecraft
        """
        version_path = VersionManager._download_version(VersionManager._choosing_version(id))

        if version_path is None:
            raise RuntimeError("Cannot download version metadata")

        version_data = VersionManager._load_version(version_path)
        version = VersionManager._parse_version(version_data, version_path)
        if version is None:
            raise RuntimeError(f"Invalid metadata for Minecraft version '{id}'.")
        return version
    


    @staticmethod
    def _choosing_version(id:str) -> VersionManifestManager:
        versions = VersionManifestManager.get()
        version = next((version for version in versions if version.id == id), None)
        if version is None:
            raise RuntimeError(f"Minecraft version '{id}' was not found in the manifest.")
        return version

    @staticmethod
    def _download_version(version:VersionManifestManager) -> Path | None:
        version_path = Paths.version_json(version)
        version_path.parent.mkdir(parents=True,exist_ok=True)
        try:
            req = requests.get(version.url, timeout=10)
            version_path.write_text(req.text, encoding="utf-8")
            return version_path
        except requests.RequestException:
            return None
    
    @staticmethod
    def _load_version(path:Path) -> dict:
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return {}
    @staticmethod
    def _parse_version(version_data:dict,version_path:str) -> Version | None:
        try:
            # print(version_data) -> for debugging
            return Version(
                id=version_data["id"],
                arguments=version_data.get("arguments"),
                minecraft_arguments=version_data.get(
                    "minecraftArguments"
                ),
                libraries=version_data["libraries"],
                downloads=version_data["downloads"],
                asset_index=version_data["assetIndex"],
                assets= version_data["assets"],
                main_class=version_data["mainClass"],
                java_version=version_data.get("javaVersion", {"component": "jre-legacy","majorVersion": 8,}),
                raw_json=version_data,
                path=version_path,
                type=version_data.get("type", "release"),
                
                
            )
        except (KeyError, TypeError, ValueError):
            return None

