from __future__ import annotations

from time import time

from src.core.auth.microsoft.microsoft_account_authenticator import MicrosoftAccountAuthenticator
from src.core.auth.microsoft.microsoft_auth_config import MicrosoftAuthConfig
from src.core.auth.microsoft.microsoft_auth_gate import MicrosoftAuthenticationGate
from src.core.auth.offline_auth import OfflineAuthentication
from src.models.account.account import Account
from src.models.account.account_source import AccountSource
from src.models.auth.authentication import Authentication


class AccountAuthentication:
    TOKEN_REFRESH_MARGIN_SECONDS = 120

    @staticmethod
    def authenticate(account: Account) -> Authentication:
        if account.account_type is AccountSource.OFFLINE:
            return OfflineAuthentication.authenticate(account)

        if account.account_type is AccountSource.MICROSOFT:
            return AccountAuthentication._authenticate_microsoft(account)

        raise RuntimeError(f"Unsupported account type: {account.account_type!r}")

    @staticmethod
    def _authenticate_microsoft(account: Account) -> Authentication:
        MicrosoftAuthenticationGate.require_enabled()

        if AccountAuthentication._needs_refresh(account):
            account = MicrosoftAccountAuthenticator.refresh(account)
            AccountAuthentication._save_account(account)

        access_token = str(account.access_token or "").strip()
        if not access_token:
            raise RuntimeError("The Microsoft account does not contain a valid Minecraft access token. Sign in again.")

        profile_uuid = str(account.uuid or "").replace("-", "").strip()
        if len(profile_uuid) != 32:
            raise RuntimeError("The Microsoft account does not contain a valid Minecraft profile UUID. Sign in again.")

        client_id = str(MicrosoftAuthConfig.CLIENT_ID or "").strip() or "0"

        return Authentication(
            player_name=account.username,
            uuid=profile_uuid,
            access_token=access_token,
            xuid="0",
            client_id=client_id,
            user_type="msa",
        )

    @staticmethod
    def _needs_refresh(account: Account) -> bool:
        if not str(account.access_token or "").strip():
            return True

        expires_at = account.token_expires_at
        if expires_at is None:
            return False

        return int(expires_at) <= int(time()) + AccountAuthentication.TOKEN_REFRESH_MARGIN_SECONDS

    @staticmethod
    def _save_account(account: Account) -> None:
        from src.core.account.repository.account_repository import AccountRepository

        AccountRepository.save(account)
