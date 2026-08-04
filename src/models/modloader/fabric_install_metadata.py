from dataclasses import dataclass

from src.models.modloader.fabric_component import FabricComponent


@dataclass(frozen=True, slots=True)
class FabricInstallMetadata:
    game: FabricComponent
    intermediary: FabricComponent
    loader: FabricComponent
    main_class: str
    libraries: tuple[dict, ...]
