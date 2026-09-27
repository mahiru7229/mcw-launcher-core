from __future__ import annotations

from enum import StrEnum
from typing import Mapping


class JvmPresetId(StrEnum):
    CUSTOM = "custom"
    DEFAULT = "default"
    AIKAR = "aikar"
    ZGC = "zgc"
    SHENANDOAH = "shenandoah"


AIKAR_FLAGS: tuple[str, ...] = (
    "-XX:+UseG1GC",
    "-XX:+ParallelRefProcEnabled",
    "-XX:MaxGCPauseMillis=200",
    "-XX:+UnlockExperimentalVMOptions",
    "-XX:+DisableExplicitGC",
    "-XX:+AlwaysPreTouch",
    "-XX:G1NewSizePercent=30",
    "-XX:G1MaxNewSizePercent=40",
    "-XX:G1ReservePercent=20",
    "-XX:G1HeapWastePercent=5",
    "-XX:G1MixedGCCountTarget=4",
    "-XX:InitiatingHeapOccupancyPercent=15",
    "-XX:G1MixedGCLiveThresholdPercent=90",
    "-XX:G1RSetUpdatingPauseTimePercent=5",
    "-XX:SurvivorRatio=32",
    "-XX:+PerfDisableSharedMem",
    "-XX:MaxTenuringThreshold=1",
)

ZGC_FLAGS: tuple[str, ...] = (
    "-XX:+UseZGC",
    "-XX:+ZGenerational",
    "-XX:+AlwaysPreTouch",
    "-XX:+DisableExplicitGC",
)

SHENANDOAH_FLAGS: tuple[str, ...] = (
    "-XX:+UseShenandoahGC",
    "-XX:+AlwaysPreTouch",
    "-XX:+DisableExplicitGC",
    "-XX:ShenandoahGCHeuristics=adaptive",
)

PRESET_FLAGS: Mapping[str, tuple[str, ...]] = {
    JvmPresetId.DEFAULT: (),
    JvmPresetId.AIKAR: AIKAR_FLAGS,
    JvmPresetId.ZGC: ZGC_FLAGS,
    JvmPresetId.SHENANDOAH: SHENANDOAH_FLAGS,
}


def get_preset_flags(preset_id: str) -> list[str]:
    normalized = str(preset_id or "").strip().casefold()
    return list(PRESET_FLAGS.get(normalized, ()))


def detect_preset(flags: list[str] | tuple[str, ...]) -> str:
    normalized = tuple(str(f).strip() for f in flags if str(f).strip())
    if not normalized:
        return JvmPresetId.DEFAULT

    for preset_id, preset_flags in PRESET_FLAGS.items():
        if preset_id == JvmPresetId.DEFAULT:
            continue
        if normalized == preset_flags:
            return preset_id

    return JvmPresetId.CUSTOM
