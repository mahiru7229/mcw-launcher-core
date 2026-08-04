from dataclasses import dataclass


@dataclass
class PackageMetadata:
    format: str
    format_version: int
    package_type: str
    launcher_name: str
    launcher_version: str
    created_at: str
    include_saves: bool
    instance_name: str = ""
    instance_icon: str = ""
