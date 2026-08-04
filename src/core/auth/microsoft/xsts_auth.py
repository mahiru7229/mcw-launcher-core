import httpx

from src.models.auth.microsoft.xbox_user_token import XboxUserToken
from src.models.auth.microsoft.xsts_token import XSTSToken


class XSTSAuthentication:

    AUTH_URL = "https://xsts.auth.xboxlive.com/xsts/authorize"

    @staticmethod
    def authenticate(xbox_token: XboxUserToken) -> XSTSToken:
        if not xbox_token.token:
            raise ValueError("Xbox user token cannot be empty.")

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-xbl-contract-version": "1"
        }

        payload = {
            "Properties": {
                "SandboxId": "RETAIL",
                "UserTokens": [
                    xbox_token.token
                ]
            },
            "RelyingParty": "rp://api.minecraftservices.com/",
            "TokenType": "JWT"
        }

        try:
            response = httpx.post(
                XSTSAuthentication.AUTH_URL,
                headers=headers,
                json=payload,
                timeout=30.0
            )

            response.raise_for_status()

        except httpx.HTTPStatusError as e:
            error_data = XSTSAuthentication._read_error(e.response)

            raise RuntimeError(
                XSTSAuthentication._format_error(error_data)
            ) from e

        except httpx.HTTPError as e:
            raise RuntimeError(
                "Could not connect to XSTS authentication."
            ) from e

        return XSTSToken.from_dict(response.json())

    @staticmethod
    def _read_error(response: httpx.Response) -> dict:
        try:
            data = response.json()

            if isinstance(data, dict):
                return data

        except ValueError:
            pass

        return {
            "status_code": response.status_code,
            "message": response.text
        }

    @staticmethod
    def _format_error(error_data: dict) -> str:
        xerr = error_data.get("XErr")

        known_errors = {
            2148916233: (
                "This Microsoft account does not have an Xbox profile."
            ),
            2148916235: (
                "Xbox Live is unavailable in this account's region."
            ),
            2148916236: (
                "This account requires adult verification."
            ),
            2148916237: (
                "This account requires adult verification."
            ),
            2148916238: (
                "This account is underage and must be added to a Microsoft family."
            ),
        }

        message = known_errors.get(
            xerr,
            error_data.get("Message", "XSTS authentication failed.")
        )

        return f"XSTS authentication failed: {message}"