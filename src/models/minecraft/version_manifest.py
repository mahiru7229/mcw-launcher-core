
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

@dataclass(slots=True)
class VersionManifest:
    id: str
    type: str
    url: str
    release_time: datetime
    sha1: str = ""
    size: int = 0
