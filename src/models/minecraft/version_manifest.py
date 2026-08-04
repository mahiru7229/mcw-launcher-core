
from dataclasses import dataclass
import datetime


@dataclass(slots=True)
class VersionManifest:
    id:str
    type:str
    url:str
    release_time: datetime