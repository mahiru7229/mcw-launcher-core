from dataclasses import dataclass


@dataclass(slots=True)
class OAuthSession:
    authorization_url: str
    code_verifier: str
    state: str