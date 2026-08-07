from importlib.metadata import PackageNotFoundError, version

import mcw_core
from mcw_core import LaunchRequest, get_default_core
from mcw_core.api.config.managed_content_policy import ManagedContentPolicy
from mcw_core.api.hardware.first_run_recommendation_service import FirstRunRecommendationService
from mcw_core.api.theme.theme_palette import DEFAULT_THEME_PALETTE, derive_custom_text, is_readable_text


def test_bundled_core_runtime_version_follows_launcher_release() -> None:
    assert mcw_core.__version__ == "1.1.2"


def test_distribution_version_when_installed() -> None:
    try:
        installed = version("mcw-core")
    except PackageNotFoundError:
        return
    assert installed == "1.1.2"


def test_optifine_public_api_is_import_only() -> None:
    service = get_default_core().optifine
    assert callable(service.inspect_file)
    assert not hasattr(service, "list_versions")


def test_new_public_api_defaults() -> None:
    assert ManagedContentPolicy.ASK == "ask"
    assert LaunchRequest.__dataclass_fields__["allow_compatibility_issues_once"].default is False
    recommendation = FirstRunRecommendationService.fallback()
    assert recommendation.recommended_max_memory_mb >= recommendation.recommended_min_memory_mb


def test_custom_text_palette_preserves_readability_helpers() -> None:
    palette = derive_custom_text(DEFAULT_THEME_PALETTE, "#f0e8ff")
    assert palette.text_primary == "#f0e8ff"
    assert isinstance(is_readable_text(palette.text_primary, "#20231f"), bool)
