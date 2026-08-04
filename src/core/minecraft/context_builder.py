from src.core.fs.paths import Paths
from src.models.minecraft.version import Version
from src.core.minecraft.classpath_builder import ClasspathBuilder
from src.models.instance.instance import Instance
from src.models.auth.authentication import Authentication
from pathlib import Path
import os


class ContextBuilder:

    @staticmethod
    def build(instance:Instance,version:Version, player_data:Authentication):
        libraries_directory = Paths.libraries()
        classpath = ClasspathBuilder.build(
            version,
            Paths.client(version),
            libraries_directory
        )
        return {
            "classpath": classpath,
            "library_directory": str(libraries_directory),
            "classpath_separator": os.pathsep,
            "natives_directory": str(Paths.natives(version)),
            "launcher_name": "mcw-launcher",
            "launcher_version": "1.0",

            "game_directory": str(Paths.load_instance_dir(instance.name)),
            "assets_root": str(Paths.assets_dir()),
            "assets_index_name": version.assets,

            "version_name": version.id,

            "auth_player_name": player_data.player_name,
            "auth_uuid": player_data.uuid,
            "auth_access_token": player_data.access_token,
            "user_properties": "{}",
            "auth_xuid": player_data.xuid,
            "clientid": player_data.client_id,

            "version_type": version.raw_json.get("type", "release"),
            "user_type": getattr(player_data, "user_type", "legacy")
        }