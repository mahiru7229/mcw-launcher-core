from dataclasses import dataclass


@dataclass(slots=True)
class MicrosoftOAuthToken:
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str
    scope: str

    @staticmethod
    def from_dict(data: dict) -> "MicrosoftOAuthToken":
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        expires_in = data.get("expires_in")
        token_type = data.get("token_type")
        scope = data.get("scope", "")

        if not isinstance(access_token, str) or not access_token:
            raise ValueError("Microsoft access token is missing.")

        if not isinstance(refresh_token, str) or not refresh_token:
            raise ValueError("Microsoft refresh token is missing.")

        if not isinstance(expires_in, int):
            raise ValueError("Microsoft token expiry is invalid.")

        if not isinstance(token_type, str) or not token_type:
            raise ValueError("Microsoft token type is missing.")

        return MicrosoftOAuthToken(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            token_type=token_type,
            scope=scope
        )