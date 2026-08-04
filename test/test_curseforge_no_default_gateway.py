from src.config import CURSEFORGE_DEFAULT_GATEWAY_URL
from src.core.config.curseforge_config_manager import CurseForgeConfigManager


def test_no_default_curseforge_gateway_is_bundled(monkeypatch, tmp_path):
    for name in (
        CurseForgeConfigManager.ENV_GATEWAY_URL,
        CurseForgeConfigManager.ENV_CLIENT_TOKEN,
        *(f"{CurseForgeConfigManager.ENV_GATEWAY_URL_PREFIX}{index}" for index in range(1, CurseForgeConfigManager.MAX_GATEWAYS + 1)),
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(CurseForgeConfigManager, "path", staticmethod(lambda: tmp_path / "private.json"))
    monkeypatch.setattr(CurseForgeConfigManager, "legacy_path", staticmethod(lambda: tmp_path / "legacy.json"))

    assert CURSEFORGE_DEFAULT_GATEWAY_URL == ""
    assert CurseForgeConfigManager.gateway_urls() == ()
    assert CurseForgeConfigManager.is_configured() is False
