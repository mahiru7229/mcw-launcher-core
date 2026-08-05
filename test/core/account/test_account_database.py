import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path

from src.core.account.database.account_database import AccountDatabase
from src.core.fs.paths import Paths


@contextmanager
def _sqlite_session(database_path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(database_path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _use_temporary_database(monkeypatch, tmp_path):
    accounts_root = tmp_path / "accounts"
    monkeypatch.setattr(Paths, "ACCOUNTS_ROOT", accounts_root)
    return accounts_root / "accounts.db"


def test_initialize_creates_database_and_tables(monkeypatch, tmp_path) -> None:
    database_path = _use_temporary_database(monkeypatch, tmp_path)

    result = AccountDatabase.initialize()

    assert result == database_path
    assert database_path.is_file()

    with _sqlite_session(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        schema_version = connection.execute("PRAGMA user_version").fetchone()[0]

    assert {"accounts", "account_state"}.issubset(tables)
    assert schema_version == AccountDatabase.SCHEMA_VERSION


def test_connect_repairs_an_empty_database(monkeypatch, tmp_path) -> None:
    database_path = _use_temporary_database(monkeypatch, tmp_path)
    database_path.parent.mkdir(parents=True)

    sqlite3.connect(database_path).close()

    with AccountDatabase.session() as connection:
        account_count = connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]

    assert account_count == 0


def test_initialize_migrates_legacy_token_columns(monkeypatch, tmp_path) -> None:
    database_path = _use_temporary_database(monkeypatch, tmp_path)
    database_path.parent.mkdir(parents=True)

    with _sqlite_session(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE accounts (
                account_id TEXT PRIMARY KEY,
                account_type TEXT NOT NULL,
                username TEXT NOT NULL,
                uuid TEXT NOT NULL
            )
            """
        )

    AccountDatabase.initialize()

    with _sqlite_session(database_path) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(accounts)").fetchall()
        }

    assert {"access_token", "refresh_token", "token_expires_at"}.issubset(columns)


def test_connect_enables_security_pragmas(monkeypatch, tmp_path) -> None:
    _use_temporary_database(monkeypatch, tmp_path)

    with AccountDatabase.session() as connection:
        secure_delete = connection.execute("PRAGMA secure_delete").fetchone()[0]
        trusted_schema = connection.execute("PRAGMA trusted_schema").fetchone()[0]
        temp_store = connection.execute("PRAGMA temp_store").fetchone()[0]

    assert secure_delete == 1
    assert trusted_schema == 0
    assert temp_store == 2


def test_session_closes_connection(monkeypatch, tmp_path) -> None:
    _use_temporary_database(monkeypatch, tmp_path)

    with AccountDatabase.session() as connection:
        connection.execute("SELECT 1")

    try:
        connection.execute("SELECT 1")
    except sqlite3.ProgrammingError as error:
        assert "closed" in str(error).casefold()
    else:
        raise AssertionError("AccountDatabase.session() left the SQLite connection open")
