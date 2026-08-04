from src.config import MICROSOFT_CLIENT_ID


class MicrosoftAuthConfig:
    CLIENT_ID = str(MICROSOFT_CLIENT_ID or "").strip()
    TENANT = "consumers"

    AUTHORIZE_URL = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/authorize"
    TOKEN_URL = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token"

    REDIRECT_URI = "http://localhost:8400"

    SCOPES = [
        "XboxLive.signin",
        "offline_access"
    ]
