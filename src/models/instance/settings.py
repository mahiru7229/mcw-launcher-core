from pathlib import Path
from dataclasses import dataclass, field



@dataclass(slots=True)
class InstanceSettings:
    java_path: Path
    min_memory: int = 1024
    max_memory: int = 2048

    jvm_arguments: list[str] = field(default_factory=list)
    game_arguments: list[str] = field(default_factory=list)

    offline_multiplayer_enabled: bool = False
    lan_auth_mode: str = "microsoft_only"
    lan_connection_provider: str = "manual"
    modrinth_failure_policy: str = "inherit"
    curseforge_failure_policy: str = "inherit"
    forge_preflight_failure_policy: str = "inherit"

    width: int = 854
    height: int = 480
    fullscreen: bool = False