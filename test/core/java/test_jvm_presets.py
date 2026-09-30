from __future__ import annotations

from mcw_core.api.java.jvm_presets import (
    AIKAR_FLAGS,
    SHENANDOAH_FLAGS,
    ZGC_FLAGS,
    JvmPresetId,
    detect_preset,
    get_preset_flags,
)


def test_jvm_preset_ids():
    assert JvmPresetId.CUSTOM == "custom"
    assert JvmPresetId.DEFAULT == "default"
    assert JvmPresetId.AIKAR == "aikar"
    assert JvmPresetId.ZGC == "zgc"
    assert JvmPresetId.SHENANDOAH == "shenandoah"


def test_get_preset_flags():
    assert get_preset_flags(JvmPresetId.DEFAULT) == []
    assert get_preset_flags("") == []
    assert get_preset_flags("unknown_preset") == []
    assert get_preset_flags(JvmPresetId.AIKAR) == list(AIKAR_FLAGS)
    assert get_preset_flags(JvmPresetId.ZGC) == list(ZGC_FLAGS)
    assert get_preset_flags(JvmPresetId.SHENANDOAH) == list(SHENANDOAH_FLAGS)


def test_detect_preset():
    assert detect_preset([]) == JvmPresetId.DEFAULT
    assert detect_preset(["  ", ""]) == JvmPresetId.DEFAULT
    assert detect_preset(list(AIKAR_FLAGS)) == JvmPresetId.AIKAR
    assert detect_preset(list(ZGC_FLAGS)) == JvmPresetId.ZGC
    assert detect_preset(list(SHENANDOAH_FLAGS)) == JvmPresetId.SHENANDOAH
    assert detect_preset(["-Xmx4G", "-XX:+UseG1GC"]) == JvmPresetId.CUSTOM


if __name__ == "__main__":
    test_jvm_preset_ids()
    test_get_preset_flags()
    test_detect_preset()
    print("test_jvm_presets passed!")
