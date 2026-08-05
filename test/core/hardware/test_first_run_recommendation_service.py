from pathlib import Path

from src.core.hardware.first_run_recommendation_service import FirstRunRecommendationService
from src.core.java.java_manager import JavaManager
from src.core.system.memory import SystemMemory
from src.models.java.java import JavaInstallation
from src.models.java.java_source import JavaSource


def test_inspect_returns_conservative_ram_and_prefers_java_21(monkeypatch) -> None:
    monkeypatch.setattr(SystemMemory, "total_physical_memory_mb", classmethod(lambda cls: 16 * 1024))
    monkeypatch.setattr(FirstRunRecommendationService, "available_physical_memory_mb", staticmethod(lambda: 10 * 1024))
    monkeypatch.setattr(
        JavaManager,
        "find_installation",
        staticmethod(
            lambda: [
                JavaInstallation(17, Path("C:/Java17/bin/javaw.exe"), JavaSource.PATH),
                JavaInstallation(21, Path("C:/Java21/bin/javaw.exe"), JavaSource.REGISTRY),
                JavaInstallation(8, Path("C:/Java8/bin/javaw.exe"), JavaSource.JAVA_HOME),
            ]
        ),
    )

    result = FirstRunRecommendationService.inspect()

    assert result.total_memory_mb == 16 * 1024
    assert result.available_memory_mb == 10 * 1024
    assert result.recommended_min_memory_mb == 1024
    assert result.recommended_max_memory_mb == 6144
    assert result.java_majors == (8, 17, 21)
    assert Path(result.recommended_java_path).as_posix().endswith("Java21/bin/javaw.exe")


def test_ram_recommendation_respects_available_and_physical_limits() -> None:
    assert FirstRunRecommendationService.recommended_max_memory_mb(3072, 2048) == 1024
    assert FirstRunRecommendationService.recommended_max_memory_mb(8192, 3072) <= 1536
    assert FirstRunRecommendationService.recommended_max_memory_mb(32768, 32768) == 8192
    assert FirstRunRecommendationService.recommended_max_memory_mb(0, 0) == 2048
