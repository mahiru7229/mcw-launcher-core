from dataclasses import dataclass


@dataclass(slots=True)
class MinecraftAccessToken:
    access_token: str
    token_type: str
    expires_in: int
    username: str

    @staticmethod
    def from_dict(data: dict) -> "MinecraftAccessToken":
        access_token = data.get("access_token")
        token_type = data.get("token_type")
        expires_in = data.get("expires_in")
        username = data.get("username", "")

        if not isinstance(access_token, str) or not access_token:
            raise ValueError("Minecraft access token is missing.")

        if not isinstance(token_type, str) or not token_type:
            raise ValueError("Minecraft token type is missing.")

        if not isinstance(expires_in, int):
            raise ValueError("Minecraft token expiry is invalid.")

        return MinecraftAccessToken(
            access_token=access_token,
            token_type=token_type,
            expires_in=expires_in,
            username=username
        )