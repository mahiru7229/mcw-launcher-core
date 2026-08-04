from dataclasses import dataclass
from pathlib import Path

@dataclass(slots=True)
class DownloadClient:
    url:str
    sha1:str
    size:int