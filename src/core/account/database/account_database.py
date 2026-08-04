from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path
from threading import Lock

from src.core.fs.paths import Paths


class AccountDatabase:
    SCHEMA_VERSION = 3
    CONNECTION_TIMEOUT_SECONDS = 10.0

    _schema_lock = Lock()

    _CREATE_ACCOUNTS_TABLE = """
        CREATE TABLE IF NOT EXISTS accounts (
            account_id TEXT PRIMARY KEY,
            account_type TEXT NOT NULL,
            username TEXT NOT NULL,
            uuid TEXT NOT NULL,
            access_token TEXT,
            refresh_token TEXT,
            token_expires_at INTEGER,
            skin_url TEXT,
            skin_variant TEXT,
            token_cipher_version INTEGER NOT NULL DEFAULT 1,
            record_integrity TEXT,
            updated_at INTEGER
        )
    """

    _CREATE_ACCOUNT_STATE_TABLE = """
        CREATE TABLE IF NOT EXISTS account_state (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """

    _REQUIRED_ACCOUNT_COLUMNS = {"account_id", "account_type", "username", "uuid"}
    _MIGRATABLE_ACCOUNT_COLUMNS = {
        "access_token": "TEXT",
        "refresh_token": "TEXT",
        "token_expires_at": "INTEGER",
        "skin_url": "TEXT",
        "skin_variant": "TEXT",
        "token_cipher_version": "INTEGER NOT NULL DEFAULT 1",
        "record_integrity": "TEXT",
        "updated_at": "INTEGER",
    }

    @staticmethod
    def initialize() -> Path:
        database_path = AccountDatabase._prepare_database_path()
        with AccountDatabase.session() as connection:
            connection.execute("SELECT 1")
        return database_path

    @staticmethod
    def connect() -> sqlite3.Connection:
        database_path = AccountDatabase._prepare_database_path()
        connection: sqlite3.Connection | None = None

        try:
            connection = sqlite3.connect(database_path, timeout=AccountDatabase.CONNECTION_TIMEOUT_SECONDS)
            connection.row_factory = sqlite3.Row
            AccountDatabase._configure_connection(connection)
            AccountDatabase._verify_integrity(connection)

            with AccountDatabase._schema_lock:
                AccountDatabase._ensure_schema(connection)
                connection.commit()

            return connection
        except (sqlite3.Error, RuntimeError) as error:
            if connection is not None:
                connection.close()
            if isinstance(error, RuntimeError):
                raise
            raise RuntimeError(f"Cannot open the account database at '{database_path}': {error}") from error

    @staticmethod
    @contextmanager
    def session() -> Iterator[sqlite3.Connection]:
        connection = AccountDatabase.connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def verify_integrity() -> bool:
        with AccountDatabase.session() as connection:
            AccountDatabase._verify_integrity(connection)
        return True

    @staticmethod
    def secure_compact() -> None:
        database_path = AccountDatabase._prepare_database_path()
        connection = sqlite3.connect(database_path, timeout=AccountDatabase.CONNECTION_TIMEOUT_SECONDS)
        try:
            connection.execute("PRAGMA secure_delete = ON")
            connection.execute("VACUUM")
        finally:
            connection.close()

    @staticmethod
    def _configure_connection(connection: sqlite3.Connection) -> None:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA trusted_schema = OFF")
        connection.execute("PRAGMA secure_delete = ON")
        connection.execute("PRAGMA temp_store = MEMORY")
        connection.execute("PRAGMA synchronous = FULL")

    @staticmethod
    def _verify_integrity(connection: sqlite3.Connection) -> None:
        rows = connection.execute("PRAGMA quick_check").fetchall()
        messages = [str(row[0]) for row in rows]
        if messages != ["ok"]:
            detail = "; ".join(messages[:3]) or "unknown integrity error"
            raise RuntimeError(f"The account database failed its integrity check: {detail}")

    @staticmethod
    def _prepare_database_path() -> Path:
        database_path = Paths.account_database_path()
        try:
            database_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise RuntimeError(f"Cannot create the account data directory '{database_path.parent}': {error}") from error
        return database_path

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        connection.execute(AccountDatabase._CREATE_ACCOUNTS_TABLE)
        connection.execute(AccountDatabase._CREATE_ACCOUNT_STATE_TABLE)

        columns = {row["name"] for row in connection.execute("PRAGMA table_info(accounts)").fetchall()}
        missing_required = AccountDatabase._REQUIRED_ACCOUNT_COLUMNS - columns
        if missing_required:
            missing = ", ".join(sorted(missing_required))
            raise RuntimeError(f"The account database schema is invalid. Missing required columns: {missing}.")

        for column_name, column_type in AccountDatabase._MIGRATABLE_ACCOUNT_COLUMNS.items():
            if column_name not in columns:
                connection.execute(f"ALTER TABLE accounts ADD COLUMN {column_name} {column_type}")

        connection.execute("CREATE INDEX IF NOT EXISTS idx_accounts_username ON accounts(username COLLATE NOCASE)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_microsoft_uuid ON accounts(uuid COLLATE NOCASE) WHERE account_type = 'microsoft'")
        connection.execute(f"PRAGMA user_version = {AccountDatabase.SCHEMA_VERSION}")
