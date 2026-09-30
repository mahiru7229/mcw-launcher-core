from src.config import CURSEFORGE_CACHE_MAX_BYTES, CURSEFORGE_MANUAL_REFRESH_COOLDOWN_SECONDS, CURSEFORGE_USER_AGENT, MODRINTH_USER_AGENT, UPDATE_CHANNEL, VERSION, VERSION_ID, VERSION_TAG
from src.core.modrinth.modrinth_client import ModrinthClient
from src.core.package.package_manager import PackageManager
from src.gui.config import VERSION as GUI_VERSION
from src.gui.config import VERSION_ID as GUI_VERSION_ID


def test_launcher_version_metadata_has_one_source_of_truth() -> None:
    assert VERSION == f"v{VERSION_ID}"
    assert VERSION_TAG == VERSION
    assert UPDATE_CHANNEL in {"beta", "stable"}
    assert GUI_VERSION == VERSION
    assert GUI_VERSION_ID == VERSION_ID
    assert PackageManager.LAUNCHER_VERSION == VERSION_TAG
    assert ModrinthClient.USER_AGENT == MODRINTH_USER_AGENT
    assert VERSION_ID in ModrinthClient.USER_AGENT
    assert CURSEFORGE_USER_AGENT == MODRINTH_USER_AGENT
    assert CURSEFORGE_CACHE_MAX_BYTES == 10 * 1024 * 1024
    assert CURSEFORGE_MANUAL_REFRESH_COOLDOWN_SECONDS == 60
