from __future__ import annotations

import httpx

from src.models.auth.microsoft.minecraft_profile import MinecraftProfile


class MinecraftProfileClient:
    PROFILE_URL = "https://api.minecraftservices.com/minecraft/profile"
    ENTITLEMENTS_URL = "https://api.minecraftservices.com/entitlements/mcstore"

    @staticmethod
    def get_profile(access_token: str) -> MinecraftProfile:
        response = MinecraftProfileClient._get(MinecraftProfileClient.PROFILE_URL, access_token)
        if response.status_code == 404:
            raise RuntimeError("This Microsoft account does not have a Minecraft Java profile.")
        try:
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise RuntimeError("Unable to load the Minecraft profile.") from error
        if not isinstance(payload, dict):
            raise RuntimeError("Minecraft Services returned an invalid profile response.")
        return MinecraftProfile.from_dict(payload)

    @staticmethod
    def verify_entitlement(access_token: str) -> None:
        response = MinecraftProfileClient._get(MinecraftProfileClient.ENTITLEMENTS_URL, access_token)
        try:
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise RuntimeError("Unable to verify Minecraft ownership.") from error
        items = payload.get("items", []) if isinstance(payload, dict) else []
        if not isinstance(items, list) or not items:
            raise RuntimeError("This Microsoft account does not appear to own Minecraft Java Edition.")

    @staticmethod
    def _get(url: str, access_token: str) -> httpx.Response:
        if not str(access_token).strip():
            raise ValueError("Minecraft access token cannot be empty.")
        try:
            return httpx.get(url, headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"}, timeout=30.0)
        except httpx.HTTPError as error:
            raise RuntimeError("Could not connect to Minecraft Services.") from error
