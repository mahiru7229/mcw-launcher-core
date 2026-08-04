from __future__ import annotations

from src.core.account.database.account_database import AccountDatabase
from src.core.account.repository.account_repository import AccountRepository
from src.core.security.account_integrity import AccountIntegrity, AccountIntegrityError
from src.core.security.token_cipher import TokenCipher
from src.models.account.account import Account
from src.models.account.account_security_report import AccountSecurityReport
from src.models.account.account_source import AccountSource


class AccountSecurityManager:
    @classmethod
    def audit(cls) -> AccountSecurityReport:
        database_ok = AccountDatabase.verify_integrity()
        rows = AccountRepository.raw_rows()
        microsoft_count = 0
        protected_count = 0
        legacy_count = 0
        invalid_count = 0

        for row in rows:
            if str(row["account_type"]) != AccountSource.MICROSOFT.value:
                continue
            microsoft_count += 1
            if not row["refresh_token"]:
                invalid_count += 1
                continue
            if cls._row_is_legacy(row):
                legacy_count += 1
                continue
            try:
                cls._verify_row(row)
            except Exception:
                invalid_count += 1
            else:
                protected_count += 1

        return AccountSecurityReport(
            database_ok=database_ok,
            account_count=len(rows),
            microsoft_account_count=microsoft_count,
            protected_account_count=protected_count,
            legacy_account_count=legacy_count,
            invalid_account_count=invalid_count,
        )

    @classmethod
    def migrate_if_needed(cls) -> AccountSecurityReport:
        rows = AccountRepository.raw_rows()
        migrated = 0
        invalid = 0
        if not rows:
            return cls.audit()
        key_reset = cls._ensure_integrity_key()

        for row in rows:
            needs_migration = key_reset or cls._row_is_legacy(row)
            if not needs_migration:
                try:
                    cls._verify_row(row)
                except Exception:
                    needs_migration = True
                    invalid += 1
            if not needs_migration:
                continue

            try:
                account = AccountRepository.decode_raw_row(row, verify_integrity=False)
            except Exception:
                account = cls._decode_profile_only(row)
                invalid += 1
            AccountRepository.save(account)
            migrated += 1

        if migrated:
            AccountDatabase.secure_compact()
        return cls._build_result(migrated=migrated, discovered_invalid=invalid)

    @classmethod
    def migrate_and_reprotect(cls) -> AccountSecurityReport:
        rows = AccountRepository.raw_rows()
        migrated = 0
        invalid = 0
        if not rows:
            return cls.audit()
        key_reset = cls._ensure_integrity_key(force_reset=True)

        for row in rows:
            try:
                account = AccountRepository.decode_raw_row(row, verify_integrity=False if key_reset else bool(row["record_integrity"]))
            except Exception:
                account = cls._decode_profile_only(row)
                invalid += 1
            AccountRepository.save(account)
            migrated += 1

        if migrated:
            AccountDatabase.secure_compact()
        return cls._build_result(migrated=migrated, discovered_invalid=invalid)

    @classmethod
    def _build_result(cls, migrated: int, discovered_invalid: int) -> AccountSecurityReport:
        report = cls.audit()
        return AccountSecurityReport(
            database_ok=report.database_ok,
            account_count=report.account_count,
            microsoft_account_count=report.microsoft_account_count,
            protected_account_count=report.protected_account_count,
            legacy_account_count=report.legacy_account_count,
            invalid_account_count=report.invalid_account_count,
            migrated_account_count=migrated,
        )

    @staticmethod
    def _ensure_integrity_key(force_reset: bool = False) -> bool:
        with AccountDatabase.session() as connection:
            try:
                if force_reset:
                    AccountIntegrity.reset_key(connection)
                    return True
                AccountIntegrity.get_or_create_key(connection)
                return False
            except Exception:
                AccountIntegrity.reset_key(connection)
                return True

    @staticmethod
    def _verify_row(row) -> None:
        with AccountDatabase.session() as connection:
            key = AccountIntegrity.get_or_create_key(connection)
            payload = AccountRepository._integrity_payload_from_row(row)
            if not AccountIntegrity.verify(key, payload, row["record_integrity"]):
                raise AccountIntegrityError("Account record integrity check failed.")
        AccountRepository.decode_raw_row(row, verify_integrity=False)

    @staticmethod
    def _row_is_legacy(row) -> bool:
        if int(row["token_cipher_version"] or 1) < TokenCipher.VERSION:
            return True
        if not row["record_integrity"]:
            return True
        return TokenCipher.needs_upgrade(row["access_token"]) or TokenCipher.needs_upgrade(row["refresh_token"])

    @staticmethod
    def _decode_profile_only(row) -> Account:
        return Account(
            account_id=str(row["account_id"]),
            account_type=AccountSource(row["account_type"]),
            username=str(row["username"]),
            uuid=str(row["uuid"]),
            access_token=None,
            refresh_token=None,
            token_expires_at=None,
        )
