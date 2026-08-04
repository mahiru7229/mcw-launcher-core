from dataclasses import dataclass




@dataclass(slots=True)
class DownloadAsset:
    logical_name: str 
    url: str
    sha1: str
    size: int