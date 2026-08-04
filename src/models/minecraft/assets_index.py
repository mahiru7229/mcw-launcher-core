from dataclasses import dataclass




@dataclass(slots=True)
class DownloadAssetIndex:
    url: str
    sha1: str
    size: int
    id: str