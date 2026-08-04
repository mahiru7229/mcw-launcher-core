from urllib.parse import urlencode
import httpx
from src.models.auth.microsoft.microsoft_oauth_token import MicrosoftOAuthToken
import secrets
import webbrowser
from threading import Event
from src.core.auth.microsoft.oauth_callback_server import OAuthCallbackServer
from src.core.auth.microsoft.microsoft_auth_config import MicrosoftAuthConfig
from src.core.auth.microsoft.pkce import PKCE
from src.models.auth.microsoft.oauth_session import OAuthSession
from src.core.security.sensitive_data_redactor import SensitiveDataRedactor


class MicrosoftOAuth:


    @staticmethod
    def authenticate(prompt: str = "select_account", cancel_event: Event | None = None) -> MicrosoftOAuthToken:
        authorization_code, code_verifier = MicrosoftOAuth.request_authorization_code(prompt=prompt, cancel_event=cancel_event)

        return MicrosoftOAuth.exchange_code(
            authorization_code,
            code_verifier
        )

    @staticmethod
    def exchange_code(authorization_code: str, code_verifier: str) -> MicrosoftOAuthToken:
        data = {
            "client_id": MicrosoftAuthConfig.CLIENT_ID,
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": MicrosoftAuthConfig.REDIRECT_URI,
            "code_verifier": code_verifier,
            "scope": " ".join(MicrosoftAuthConfig.SCOPES),
        }

        try:
            response = httpx.post(
                MicrosoftAuthConfig.TOKEN_URL,
                data=data,
                timeout=30.0
            )

            response.raise_for_status()

        except httpx.HTTPStatusError as error:
            try:
                error_data = error.response.json()
            except ValueError:
                error_data = {}
            error_code = SensitiveDataRedactor.redact_text(error_data.get("error", "unknown_error"))
            raise RuntimeError(f"Microsoft OAuth token request failed: {error_code}") from error

        except httpx.HTTPError as e:
            raise RuntimeError(
                "Could not connect to Microsoft OAuth."
            ) from e

        return MicrosoftOAuthToken.from_dict(response.json())

    @staticmethod
    def refresh(refresh_token: str) -> MicrosoftOAuthToken:
        if not str(refresh_token).strip():
            raise ValueError("Microsoft refresh token cannot be empty.")
        data = {
            "client_id": MicrosoftAuthConfig.CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": str(refresh_token),
            "redirect_uri": MicrosoftAuthConfig.REDIRECT_URI,
            "scope": " ".join(MicrosoftAuthConfig.SCOPES),
        }
        try:
            response = httpx.post(MicrosoftAuthConfig.TOKEN_URL, data=data, timeout=30.0)
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            try:
                payload = error.response.json()
            except ValueError:
                payload = {}
            error_code = SensitiveDataRedactor.redact_text(payload.get("error", "unknown_error"))
            raise RuntimeError(f"Microsoft OAuth refresh failed: {error_code}. Sign in again if the session was revoked.") from error
        except httpx.HTTPError as error:
            raise RuntimeError("Could not connect to Microsoft OAuth.") from error
        return MicrosoftOAuthToken.from_dict(response.json())

    @staticmethod
    def request_authorization_code(prompt: str = "select_account", cancel_event: Event | None = None) -> tuple[str, str]:
        session = MicrosoftOAuth.create_session(prompt=prompt)

        opened = MicrosoftOAuth.open_browser(session)

        if not opened:
            raise RuntimeError(
                "Could not open the default browser."
            )

        authorization_code, returned_state = OAuthCallbackServer.wait_for_callback(cancel_event=cancel_event)

        if not secrets.compare_digest(
            returned_state,
            session.state
        ):
            raise RuntimeError(
                "Microsoft authorization state does not match."
            )

        return authorization_code, session.code_verifier

    @staticmethod
    def create_session(prompt: str = "select_account") -> OAuthSession:
        code_verifier = PKCE.generate_verifier()
        code_challenge = PKCE.create_challenge(code_verifier)
        state = secrets.token_urlsafe(32)

        normalized_prompt = str(prompt or "select_account").strip().lower()
        allowed_prompts = {"login", "none", "consent", "select_account"}
        if normalized_prompt not in allowed_prompts:
            raise ValueError(f"Unsupported Microsoft OAuth prompt: {prompt}")

        parameters = {
            "client_id": MicrosoftAuthConfig.CLIENT_ID,
            "response_type": "code",
            "redirect_uri": MicrosoftAuthConfig.REDIRECT_URI,
            "response_mode": "query",
            "scope": " ".join(MicrosoftAuthConfig.SCOPES),
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": state,
            "prompt": normalized_prompt,
        }

        authorization_url = (
            MicrosoftAuthConfig.AUTHORIZE_URL
            + "?"
            + urlencode(parameters)
        )

        return OAuthSession(
            authorization_url=authorization_url,
            code_verifier=code_verifier,
            state=state
        )

    @staticmethod
    def open_browser(session: OAuthSession) -> bool:
        return webbrowser.open(session.authorization_url)