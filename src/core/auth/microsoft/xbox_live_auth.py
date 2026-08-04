import httpx

from src.models.auth.microsoft.xbox_user_token import XboxUserToken


class XboxLiveAuthentication:

    AUTH_URL = "https://user.auth.xboxlive.com/user/authenticate"

    @staticmethod
    def authenticate(microsoft_access_token: str) -> XboxUserToken:
        if not microsoft_access_token:
            raise ValueError("Microsoft access token cannot be empty.")

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-xbl-contract-version": "1"
        }

        payload = {
            "Properties": {
                "AuthMethod": "RPS",
                "SiteName": "user.auth.xboxlive.com",
                "RpsTicket": f"d={microsoft_access_token}"
            },
            "RelyingParty": "http://auth.xboxlive.com",
            "TokenType": "JWT"
        }

        try:
            response = httpx.post(
                XboxLiveAuthentication.AUTH_URL,
                headers=headers,
                json=payload,
                timeout=30.0
            )

            response.raise_for_status()

        except httpx.HTTPStatusError as e:
            try:
                error_data = e.response.json()
            except ValueError:
                error_data = e.response.text

            raise RuntimeError(
                f"Xbox Live authentication failed: {error_data}"
            ) from e

        except httpx.HTTPError as e:
            raise RuntimeError(
                "Could not connect to Xbox Live authentication."
            ) from e

        return XboxUserToken.from_dict(response.json())