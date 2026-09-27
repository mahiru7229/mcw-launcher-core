from time import time, sleep
from typing import Callable
from urllib.parse import urlencode
import httpx
import shutil
from src.models.auth.microsoft.device_code_response import DeviceCodeResponse
from src.models.auth.microsoft.microsoft_oauth_token import MicrosoftOAuthToken
import secrets
import subprocess
import webbrowser
from threading import Event
from src.core.auth.microsoft.oauth_callback_server import MicrosoftAuthorizationCancelledError, OAuthCallbackServer
from src.core.auth.microsoft.microsoft_auth_config import MicrosoftAuthConfig
from src.core.auth.microsoft.pkce import PKCE
from src.models.auth.microsoft.oauth_session import OAuthSession
from src.core.security.sensitive_data_redactor import SensitiveDataRedactor
from src.core.system.platform_info import PlatformInfo


class MicrosoftOAuth:

    @staticmethod
    def authenticate(
        prompt: str = "select_account",
        cancel_event: Event | None = None,
        on_device_code: Callable[[DeviceCodeResponse], None] | None = None,
    ) -> MicrosoftOAuthToken:
        device_resp = MicrosoftOAuth.request_device_code()
        if on_device_code is not None:
            on_device_code(device_resp)
        else:
            try:
                webbrowser.open(device_resp.verification_uri)
            except Exception:
                pass

        return MicrosoftOAuth.poll_device_code_token(
            device_code=device_resp.device_code,
            interval=device_resp.interval,
            expires_in=device_resp.expires_in,
            cancel_event=cancel_event,
        )

    @staticmethod
    def request_device_code() -> DeviceCodeResponse:
        data = {
            "client_id": MicrosoftAuthConfig.CLIENT_ID,
            "scope": " ".join(MicrosoftAuthConfig.SCOPES),
        }
        try:
            response = httpx.post(
                MicrosoftAuthConfig.DEVICE_CODE_URL,
                data=data,
                timeout=30.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            try:
                error_data = error.response.json()
            except ValueError:
                error_data = {}
            error_code = SensitiveDataRedactor.redact_text(error_data.get("error", "unknown_error"))
            raise RuntimeError(f"Microsoft device code request failed: {error_code}") from error
        except httpx.HTTPError as e:
            raise RuntimeError("Could not connect to Microsoft OAuth.") from e

        return DeviceCodeResponse.from_dict(response.json())

    @staticmethod
    def poll_device_code_token(
        device_code: str,
        interval: int = 5,
        expires_in: int = 900,
        cancel_event: Event | None = None,
    ) -> MicrosoftOAuthToken:
        deadline = time() + expires_in
        poll_interval = max(interval, 1)

        while time() < deadline:
            if cancel_event is not None and cancel_event.is_set():
                raise MicrosoftAuthorizationCancelledError("Microsoft authentication was cancelled.")

            sleep_remaining = float(poll_interval)
            while sleep_remaining > 0:
                if cancel_event is not None and cancel_event.is_set():
                    raise MicrosoftAuthorizationCancelledError("Microsoft authentication was cancelled.")
                chunk = min(sleep_remaining, 0.25)
                if cancel_event is not None:
                    if cancel_event.wait(chunk):
                        raise MicrosoftAuthorizationCancelledError("Microsoft authentication was cancelled.")
                else:
                    sleep(chunk)
                sleep_remaining -= chunk

            if cancel_event is not None and cancel_event.is_set():
                raise MicrosoftAuthorizationCancelledError("Microsoft authentication was cancelled.")

            data = {
                "client_id": MicrosoftAuthConfig.CLIENT_ID,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
            }

            try:
                response = httpx.post(
                    MicrosoftAuthConfig.TOKEN_URL,
                    data=data,
                    timeout=10.0,
                )
            except httpx.HTTPError:
                continue

            if response.status_code == 200:
                return MicrosoftOAuthToken.from_dict(response.json())

            try:
                payload = response.json()
            except Exception:
                payload = {}

            error_code = payload.get("error", "")

            if error_code == "authorization_pending":
                continue
            elif error_code == "slow_down":
                poll_interval += 5
                continue
            elif error_code == "expired_token":
                raise TimeoutError("The Microsoft device authorization code has expired. Please try again.")
            elif error_code == "access_denied":
                raise MicrosoftAuthorizationCancelledError("Authorization was cancelled or denied.")
            else:
                redacted = SensitiveDataRedactor.redact_text(error_code or response.text)
                raise RuntimeError(f"Microsoft OAuth failed: {redacted}")

        raise TimeoutError("Microsoft device authorization timed out.")

    @staticmethod
    def authenticate_browser(prompt: str = "select_account", cancel_event: Event | None = None) -> MicrosoftOAuthToken:
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
        if webbrowser.open(session.authorization_url):
            return True

        if PlatformInfo.current().os_name != "linux":
            return False

        opener = shutil.which("xdg-open")
        if not opener:
            return False
        try:
            subprocess.Popen(
                [opener, session.authorization_url],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            return False
        return True
