from dataclasses import dataclass
from pathlib import Path
@dataclass(slots=True)
class Version:
    id: str
    path: Path
    libraries: list
    downloads: dict
    asset_index: dict
    assets: str
    main_class: str
    java_version: dict
    raw_json: dict
    type:str



    #for legacy version support
    arguments: dict |  None
    minecraft_arguments: str | None