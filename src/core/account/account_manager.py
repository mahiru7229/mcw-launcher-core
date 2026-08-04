from threading import Event
import uuid

from src.core.auth.offline_auth import OfflineAuthentication
from src.core.account.repository.account_repository import AccountRepository
from src.core.account.account_skin_manager import AccountSkinManager
from src.models.account.account import Account
from src.models.account.account_source import AccountSource
from src.core.auth.microsoft.microsoft_account_authenticator import MicrosoftAccountAuthenticator


class AccountManager:

    @staticmethod
    def create_offline_account(username: str) -> Account:
        username = str(username or "").strip()
        if not username:
            raise ValueError("Username cannot be empty.")

        if AccountManager.is_account_exist(username):
            raise RuntimeError(
                f"Account '{username}' already exists."
            )

        account = Account(
            account_id=str(uuid.uuid4()),
            account_type=AccountSource.OFFLINE,
            username=username,
            uuid=OfflineAuthentication.uuid_generator(username)
        )

        AccountRepository.save(account)

        if AccountRepository.get_selected_account() is None:
            AccountRepository.set_selected_account(account.account_id)

        return account

    @staticmethod
    def create_microsoft_account(cancel_event: Event | None = None) -> Account:
        authenticated_account = MicrosoftAccountAuthenticator.authenticate() if cancel_event is None else MicrosoftAccountAuthenticator.authenticate(cancel_event=cancel_event)
        existing_account = AccountManager._find_microsoft_account_by_uuid(authenticated_account.uuid)

        if existing_account is not None:
            existing_account.username = authenticated_account.username
            existing_account.uuid = authenticated_account.uuid
            existing_account.access_token = authenticated_account.access_token
            existing_account.refresh_token = authenticated_account.refresh_token
            existing_account.token_expires_at = authenticated_account.token_expires_at
            existing_account.skin_url = authenticated_account.skin_url
            existing_account.skin_variant = authenticated_account.skin_variant
            account = existing_account
        else:
            account = authenticated_account

        AccountRepository.save(account)
        AccountRepository.set_selected_account(account.account_id)
        return account

    @staticmethod
    def _find_microsoft_account_by_uuid(profile_uuid: str) -> Account | None:
        normalized_uuid = AccountManager._normalize_uuid(profile_uuid)
        if not normalized_uuid:
            return None

        for account in AccountRepository.list_accounts():
            if account.account_type is not AccountSource.MICROSOFT:
                continue
            if AccountManager._normalize_uuid(account.uuid) == normalized_uuid:
                return account

        return None

    @staticmethod
    def _normalize_uuid(value: str | None) -> str:
        return str(value or "").replace("-", "").strip().casefold()

    @staticmethod
    def list_accounts() -> list[Account]:
        return AccountRepository.list_accounts()

    @staticmethod
    def get_account(account_id: str) -> Account | None:
        return AccountRepository.get(account_id)

    @staticmethod
    def get_selected_account() -> Account | None:
        selected_account = AccountRepository.get_selected_account()

        if selected_account is not None:
            return selected_account

        accounts = AccountRepository.list_accounts()

        if not accounts:
            return None

        first_account = accounts[0]
        AccountRepository.set_selected_account(first_account.account_id)

        return first_account

    @staticmethod
    def set_selected_account(account_id: str) -> bool:
        return AccountRepository.set_selected_account(account_id)

    @staticmethod
    def synchronize_microsoft_profile(account_id: str) -> Account:
        account = AccountRepository.get(account_id)
        if account is None:
            raise RuntimeError("Account was not found.")
        if account.account_type is not AccountSource.MICROSOFT:
            return account
        account = MicrosoftAccountAuthenticator.synchronize_profile(account)
        AccountRepository.save(account)
        return account

    @staticmethod
    def remove_account(account_id: str) -> bool:
        selected_account = AccountRepository.get_selected_account()

        account_to_remove = AccountRepository.get(account_id)
        removed = AccountRepository.remove(account_id)

        if not removed:
            return False

        if account_to_remove is not None:
            try:
                AccountSkinManager.remove_cached_texture(account_to_remove)
            except OSError:
                pass

        if selected_account is None:
            return True

        if selected_account.account_id != account_id:
            return True

        remaining_accounts = AccountRepository.list_accounts()

        if remaining_accounts:
            AccountRepository.set_selected_account(
                remaining_accounts[0].account_id
            )

        return True

    @staticmethod
    def is_account_exist(username: str) -> bool:
        normalized_username = username.casefold()

        for account in AccountRepository.list_accounts():
            if account.username.casefold() == normalized_username:
                return True

        return False