from __future__ import annotations

import sqlite3
from time import time

from src.config import PERSIST_MICROSOFT_ACCESS_TOKEN
from src.core.account.database.account_database import AccountDatabase
from src.core.security.account_integrity import AccountIntegrity, AccountIntegrityError
from src.core.security.token_cipher import TokenCipher
from src.models.account.account import Account
from src.models.account.account_source import AccountSource


class AccountRepository:
    SELECTED_ACCOUNT_KEY = "selected_account_id"

    @staticmethod
    def save(account: Account) -> None:
        persisted_access_token = account.access_token
        if account.account_type is AccountSource.MICROSOFT and not PERSIST_MICROSOFT_ACCESS_TOKEN:
            persisted_access_token = None

        access_token = TokenCipher.encrypt(persisted_access_token, AccountRepository._purpose(account.account_id, "access")) if persisted_access_token else None
        refresh_token = TokenCipher.encrypt(account.refresh_token, AccountRepository._purpose(account.account_id, "refresh")) if account.refresh_token else None
        cipher_version = TokenCipher.VERSION
        updated_at = int(time())

        with AccountDatabase.session() as connection:
            key = AccountIntegrity.get_or_create_key(connection)
            payload = AccountRepository._integrity_payload(
                account_id=account.account_id,
                account_type=account.account_type.value,
                username=account.username,
                uuid=account.uuid,
                access_token=access_token,
                refresh_token=refresh_token,
                token_expires_at=account.token_expires_at,
                token_cipher_version=cipher_version,
                updated_at=updated_at,
            )
            signature = AccountIntegrity.sign(key, payload)
            connection.execute(
                """
                INSERT INTO accounts (
                    account_id, account_type, username, uuid, access_token, refresh_token,
                    token_expires_at, skin_url, skin_variant, token_cipher_version, record_integrity, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id) DO UPDATE SET
                    account_type = excluded.account_type,
                    username = excluded.username,
                    uuid = excluded.uuid,
                    access_token = excluded.access_token,
                    refresh_token = excluded.refresh_token,
                    token_expires_at = excluded.token_expires_at,
                    skin_url = excluded.skin_url,
                    skin_variant = excluded.skin_variant,
                    token_cipher_version = excluded.token_cipher_version,
                    record_integrity = excluded.record_integrity,
                    updated_at = excluded.updated_at
                """,
                (
                    account.account_id,
                    account.account_type.value,
                    account.username,
                    account.uuid,
                    access_token,
                    refresh_token,
                    account.token_expires_at,
                    account.skin_url,
                    account.skin_variant,
                    cipher_version,
                    signature,
                    updated_at,
                ),
            )

    @staticmethod
    def get(account_id: str) -> Account | None:
        with AccountDatabase.session() as connection:
            row = connection.execute(AccountRepository._SELECT_COLUMNS + " WHERE account_id = ?", (account_id,)).fetchone()
            if row is None:
                return None
            return AccountRepository._row_to_account(connection, row)

    @staticmethod
    def list_accounts() -> list[Account]:
        with AccountDatabase.session() as connection:
            rows = connection.execute(AccountRepository._SELECT_COLUMNS + " ORDER BY username COLLATE NOCASE ASC").fetchall()
            return [AccountRepository._row_to_account(connection, row) for row in rows]

    @staticmethod
    def remove(account_id: str) -> bool:
        removed = False
        with AccountDatabase.session() as connection:
            connection.execute(
                "UPDATE accounts SET access_token = NULL, refresh_token = NULL, token_expires_at = NULL, record_integrity = NULL WHERE account_id = ?",
                (account_id,),
            )
            cursor = connection.execute("DELETE FROM accounts WHERE account_id = ?", (account_id,))
            removed = cursor.rowcount > 0
            if removed:
                connection.execute(
                    "DELETE FROM account_state WHERE key = ? AND value = ?",
                    (AccountRepository.SELECTED_ACCOUNT_KEY, account_id),
                )
        if removed:
            try:
                AccountDatabase.secure_compact()
            except Exception:
                pass
        return removed

    @staticmethod
    def set_selected_account(account_id: str) -> bool:
        if AccountRepository.get(account_id) is None:
            return False
        with AccountDatabase.session() as connection:
            connection.execute(
                "INSERT INTO account_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (AccountRepository.SELECTED_ACCOUNT_KEY, account_id),
            )
        return True

    @staticmethod
    def get_selected_account() -> Account | None:
        with AccountDatabase.session() as connection:
            row = connection.execute("SELECT value FROM account_state WHERE key = ?", (AccountRepository.SELECTED_ACCOUNT_KEY,)).fetchone()
        if row is None:
            return None
        return AccountRepository.get(row["value"])

    @staticmethod
    def raw_rows() -> list[sqlite3.Row]:
        with AccountDatabase.session() as connection:
            return connection.execute(AccountRepository._SELECT_COLUMNS + " ORDER BY username COLLATE NOCASE ASC").fetchall()

    @staticmethod
    def decode_raw_row(row: sqlite3.Row, verify_integrity: bool = True) -> Account:
        with AccountDatabase.session() as connection:
            return AccountRepository._row_to_account(connection, row, verify_integrity=verify_integrity)

    _SELECT_COLUMNS = """
        SELECT account_id, account_type, username, uuid, access_token, refresh_token,
               token_expires_at, skin_url, skin_variant, token_cipher_version, record_integrity, updated_at
        FROM accounts
    """

    @staticmethod
    def _row_to_account(connection: sqlite3.Connection, row: sqlite3.Row, verify_integrity: bool = True) -> Account:
        payload = AccountRepository._integrity_payload_from_row(row)
        if verify_integrity and row["record_integrity"]:
            key = AccountIntegrity.get_or_create_key(connection)
            if not AccountIntegrity.verify(key, payload, row["record_integrity"]):
                raise AccountIntegrityError(f"Stored account data for '{row['username']}' failed its integrity check. Sign in again.")

        account_id = str(row["account_id"])
        access_token = TokenCipher.decrypt(row["access_token"], AccountRepository._purpose(account_id, "access")) if row["access_token"] else None
        refresh_token = TokenCipher.decrypt(row["refresh_token"], AccountRepository._purpose(account_id, "refresh")) if row["refresh_token"] else None
        return Account(
            account_id=account_id,
            account_type=AccountSource(row["account_type"]),
            username=row["username"],
            uuid=row["uuid"],
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=row["token_expires_at"],
            skin_url=row["skin_url"],
            skin_variant=row["skin_variant"],
        )

    @staticmethod
    def _purpose(account_id: str, token_type: str) -> str:
        return f"account:{str(account_id).strip().casefold()}:{token_type}"

    @staticmethod
    def _integrity_payload_from_row(row: sqlite3.Row) -> dict:
        return AccountRepository._integrity_payload(
            account_id=row["account_id"],
            account_type=row["account_type"],
            username=row["username"],
            uuid=row["uuid"],
            access_token=row["access_token"],
            refresh_token=row["refresh_token"],
            token_expires_at=row["token_expires_at"],
            token_cipher_version=row["token_cipher_version"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _integrity_payload(**values) -> dict:
        return {
            "account_id": str(values.get("account_id") or ""),
            "account_type": str(values.get("account_type") or ""),
            "username": str(values.get("username") or ""),
            "uuid": str(values.get("uuid") or "").replace("-", "").casefold(),
            "access_token": str(values.get("access_token") or ""),
            "refresh_token": str(values.get("refresh_token") or ""),
            "token_expires_at": values.get("token_expires_at"),
            "token_cipher_version": int(values.get("token_cipher_version") or 1),
            "updated_at": values.get("updated_at"),
        }
