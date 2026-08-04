from pathlib import Path
from dataclasses import dataclass



@dataclass(slots=True)
class DownloadLibrary:
    url:str
    sha1:str
    size:int
    path:Path
    is_native: bool = False