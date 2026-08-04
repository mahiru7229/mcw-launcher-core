from dataclasses import dataclass



@dataclass(slots=True)
class MicrosoftOAuthResponse:
    access_token: str
    refresh_token: str
    expires_in: int
    scope: str
    token_type: str