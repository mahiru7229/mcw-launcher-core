from __future__ import annotations

from threading import Event
from time import time
from uuid import uuid4

from src.core.account.account_skin_manager import AccountSkinManager
from src.core.auth.microsoft.microsoft_auth_gate import MicrosoftAuthenticationGate
from src.core.auth.microsoft.microsoft_auth_config import MicrosoftAuthConfig
from src.core.auth.microsoft.microsoft_oauth import MicrosoftOAuth
from src.core.auth.microsoft.minecraft_profile_client import MinecraftProfileClient
from src.core.auth.microsoft.minecraft_services_auth import MinecraftServicesAuthentication
from src.core.auth.microsoft.xbox_live_auth import XboxLiveAuthentication
from src.core.auth.microsoft.xsts_auth import XSTSAuthentication
from src.models.account.account import Account
from src.models.account.account_source import AccountSource
from src.models.auth.microsoft.minecraft_profile import MinecraftProfile


class MicrosoftAccountAuthenticator:
    PROFILE_REFRESH_MARGIN_SECONDS = 120

    @staticmethod
    def authenticate(cancel_event: Event | None = None) -> Account:
        MicrosoftAuthenticationGate.require_enabled()
        if not str(MicrosoftAuthConfig.CLIENT_ID).strip():
            raise RuntimeError("Microsoft authentication is enabled but no client_id is configured.")
        oauth_token = MicrosoftOAuth.authenticate() if cancel_event is None else MicrosoftOAuth.authenticate(cancel_event=cancel_event)
        xbox_token = XboxLiveAuthentication.authenticate(oauth_token.access_token)
        xsts_token = XSTSAuthentication.authenticate(xbox_token)
        minecraft_token = MinecraftServicesAuthentication.authenticate(xsts_token)
        MinecraftProfileClient.verify_entitlement(minecraft_token.access_token)
        profile = MinecraftProfileClient.get_profile(minecraft_token.access_token)
        account = Account(
            account_id=str(uuid4()),
            account_type=AccountSource.MICROSOFT,
            username=profile.name,
            uuid=profile.profile_id,
            access_token=minecraft_token.access_token,
            refresh_token=oauth_token.refresh_token,
            token_expires_at=int(time()) + int(minecraft_token.expires_in),
        )
        MicrosoftAccountAuthenticator._apply_profile(account, profile)
        return account

    @staticmethod
    def refresh(account: Account) -> Account:
        MicrosoftAuthenticationGate.require_enabled()
        if not str(MicrosoftAuthConfig.CLIENT_ID).strip():
            raise RuntimeError("Microsoft authentication is enabled but no client_id is configured.")
        if account.account_type is not AccountSource.MICROSOFT or not account.refresh_token:
            raise RuntimeError("This account does not contain a Microsoft refresh token.")
        oauth_token = MicrosoftOAuth.refresh(account.refresh_token)
        xbox_token = XboxLiveAuthentication.authenticate(oauth_token.access_token)
        xsts_token = XSTSAuthentication.authenticate(xbox_token)
        minecraft_token = MinecraftServicesAuthentication.authenticate(xsts_token)
        MinecraftProfileClient.verify_entitlement(minecraft_token.access_token)
        profile = MinecraftProfileClient.get_profile(minecraft_token.access_token)
        account.access_token = minecraft_token.access_token
        account.refresh_token = oauth_token.refresh_token
        account.token_expires_at = int(time()) + int(minecraft_token.expires_in)
        MicrosoftAccountAuthenticator._apply_profile(account, profile)
        return account

    @staticmethod
    def synchronize_profile(account: Account) -> Account:
        """Refresh public profile metadata and the cached skin for an existing Microsoft account."""
        if account.account_type is not AccountSource.MICROSOFT:
            return account
        expires_at = account.token_expires_at
        needs_refresh = not str(account.access_token or "").strip()
        if expires_at is not None:
            needs_refresh = needs_refresh or int(expires_at) <= int(time()) + MicrosoftAccountAuthenticator.PROFILE_REFRESH_MARGIN_SECONDS
        if needs_refresh:
            return MicrosoftAccountAuthenticator.refresh(account)
        profile = MinecraftProfileClient.get_profile(str(account.access_token))
        MicrosoftAccountAuthenticator._apply_profile(account, profile)
        return account

    @staticmethod
    def _apply_profile(account: Account, profile: MinecraftProfile) -> None:
        account.username = profile.name
        account.uuid = profile.profile_id
        account.skin_url = profile.primary_skin_url
        account.skin_variant = profile.primary_skin_variant
        try:
            AccountSkinManager.cache_profile(profile)
        except Exception:
            # Authentication and launch must not fail merely because the texture CDN is unavailable.
            pass
