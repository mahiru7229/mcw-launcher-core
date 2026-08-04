from enum import Enum


class ProgressUnit(Enum):
    NONE = "none"
    BYTES = "bytes"
    FILES = "files"
    STEPS = "steps"