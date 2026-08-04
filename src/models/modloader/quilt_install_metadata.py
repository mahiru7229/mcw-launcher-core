from dataclasses import dataclass

from src.models.modloader.quilt_component import QuiltComponent


@dataclass(frozen=True, slots=True)
class QuiltInstallMetadata:
    game: QuiltComponent
    mappings: QuiltComponent | None
    loader: QuiltComponent
    main_class: str
    libraries: tuple[dict, ...]
