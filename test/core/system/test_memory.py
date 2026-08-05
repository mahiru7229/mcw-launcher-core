from src.core.system.memory import MemoryAllocationPolicy, SystemMemory


def test_memory_policy_limits_java_maximum_to_physical_ram() -> None:
    minimum, maximum = MemoryAllocationPolicy.normalize(4096, 32768, total_memory_mb=8192)

    assert minimum == 4096
    assert maximum == 8192


def test_memory_policy_lowers_minimum_when_maximum_is_lower() -> None:
    minimum, maximum = MemoryAllocationPolicy.normalize(6144, 4096, total_memory_mb=8192)

    assert minimum == 4096
    assert maximum == 4096


def test_memory_policy_rejects_values_above_physical_ram() -> None:
    assert MemoryAllocationPolicy.is_valid(1024, 8192, total_memory_mb=8192) is True
    assert MemoryAllocationPolicy.is_valid(1024, 8193, total_memory_mb=8192) is False


def test_memory_policy_uses_safe_fallback_when_detection_fails(monkeypatch) -> None:
    monkeypatch.setattr(SystemMemory, "total_physical_memory_mb", classmethod(lambda cls: 0))

    assert MemoryAllocationPolicy.physical_limit_mb() == MemoryAllocationPolicy.FALLBACK_PHYSICAL_LIMIT_MB


def test_memory_formatter_keeps_mb_visible() -> None:
    assert MemoryAllocationPolicy.format_mb(768) == "768 MB"
    assert MemoryAllocationPolicy.format_mb(4096) == "4 GB (4096 MB)"


def test_memory_slider_values_snap_to_256_mb_steps() -> None:
    assert MemoryAllocationPolicy.snap_mb(5000, 8192) == 5120
    assert MemoryAllocationPolicy.snap_mb(9000, 8190) == 8190
