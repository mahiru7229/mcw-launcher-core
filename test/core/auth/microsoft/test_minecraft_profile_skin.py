from src.models.auth.microsoft.minecraft_profile import MinecraftProfile


def test_profile_prefers_active_skin_and_exposes_variant() -> None:
    profile = MinecraftProfile.from_dict({
        "id": "123456781234123412341234567890ab",
        "name": "PremiumPlayer",
        "skins": [
            {"id": "old", "state": "INACTIVE", "url": "https://example.invalid/old.png", "variant": "CLASSIC"},
            {"id": "active", "state": "ACTIVE", "url": "https://example.invalid/current.png", "variant": "SLIM"},
        ],
    })

    assert profile.primary_skin_url == "https://example.invalid/current.png"
    assert profile.primary_skin_variant == "slim"
