from dataclasses import dataclass
from src.models.account.account_source import AccountSource


@dataclass(slots=True)
class Account:
    account_id: str
    account_type: AccountSource
    username: str
    uuid: str

    access_token: str | None = None
    refresh_token: str | None = None
    token_expires_at: int | None = None
    skin_url: str | None = None
    skin_variant: str | None = None
