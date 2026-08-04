from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MinecraftProfile:
    profile_id: str
    name: str
    skins: tuple[dict, ...] = ()
    capes: tuple[dict, ...] = ()


    @property
    def primary_skin(self) -> dict | None:
        active = next((skin for skin in self.skins if str(skin.get("state") or "").casefold() == "active"), None)
        return active or (self.skins[0] if self.skins else None)

    @property
    def primary_skin_url(self) -> str | None:
        skin = self.primary_skin
        value = str(skin.get("url") or "").strip() if skin is not None else ""
        return value or None

    @property
    def primary_skin_variant(self) -> str | None:
        skin = self.primary_skin
        value = str(skin.get("variant") or "").strip().casefold() if skin is not None else ""
        return value or None

    @staticmethod
    def from_dict(data: dict) -> "MinecraftProfile":
        profile_id = str(data.get("id") or "").strip()
        name = str(data.get("name") or "").strip()
        if not profile_id or not name:
            raise ValueError("Minecraft profile response is incomplete.")
        skins = tuple(item for item in data.get("skins", []) if isinstance(item, dict))
        capes = tuple(item for item in data.get("capes", []) if isinstance(item, dict))
        return MinecraftProfile(profile_id=profile_id, name=name, skins=skins, capes=capes)
