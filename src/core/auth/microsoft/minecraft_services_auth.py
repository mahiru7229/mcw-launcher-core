import httpx

from src.models.auth.microsoft.xsts_token import XSTSToken
from src.models.auth.microsoft.minecraft_access_token import MinecraftAccessToken


class MinecraftServicesAuthentication:

    AUTH_URL = (
        "https://api.minecraftservices.com/"
        "authentication/login_with_xbox"
    )

    @staticmethod
    def authenticate(xsts_token: XSTSToken) -> MinecraftAccessToken:
        if not xsts_token.token:
            raise ValueError("XSTS token cannot be empty.")

        if not xsts_token.user_hash:
            raise ValueError("XSTS user hash cannot be empty.")

        payload = {
            "identityToken": (
                f"XBL3.0 x={xsts_token.user_hash};"
                f"{xsts_token.token}"
            )
        }

        try:
            response = httpx.post(
                MinecraftServicesAuthentication.AUTH_URL,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                },
                json=payload,
                timeout=30.0
            )

            response.raise_for_status()

        except httpx.HTTPStatusError as e:
            error_data = (
                MinecraftServicesAuthentication._read_error(
                    e.response
                )
            )

            raise RuntimeError(
                "Minecraft Services authentication failed: "
                f"{error_data}"
            ) from e

        except httpx.HTTPError as e:
            raise RuntimeError(
                "Could not connect to Minecraft Services."
            ) from e

        return MinecraftAccessToken.from_dict(response.json())

    @staticmethod
    def _read_error(response: httpx.Response) -> dict | str:
        try:
            data = response.json()

            if isinstance(data, dict):
                return data

        except ValueError:
            pass

        return response.text