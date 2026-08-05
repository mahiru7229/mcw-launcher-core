import uuid

import pytest

from src.core.auth.offline_auth import OfflineAuthentication
from src.models.account.account import Account
from src.models.account.account_source import AccountSource
from src.models.auth.authentication import Authentication


def make_account(
    *,
    username: str = "Steve",
    player_uuid: str = "00000000-0000-0000-0000-000000000000",
) -> Account:
    return Account(
        account_id="account-id",
        account_type=AccountSource.OFFLINE,
        username=username,
        uuid=player_uuid,
    )


def test_authenticate_returns_authentication_model():
    account = make_account()

    result = OfflineAuthentication.authenticate(account)

    assert isinstance(result, Authentication)


def test_authenticate_rebuilds_compact_offline_uuid_from_username():
    account = make_account(
        username="Mahiru",
        player_uuid="12345678-1234-5678-9234-567812345678",
    )

    result = OfflineAuthentication.authenticate(account)

    assert result.player_name == "Mahiru"
    assert result.uuid == OfflineAuthentication.uuid_generator("Mahiru").replace("-", "")
    assert len(result.uuid) == 32
    assert "-" not in result.uuid


def test_authenticate_uses_offline_placeholder_tokens():
    result = OfflineAuthentication.authenticate(
        make_account()
    )

    assert result.access_token == "0"
    assert result.xuid == ""
    assert result.client_id == ""
    assert result.user_type == "legacy"


def test_authenticate_strips_username_before_building_identity():
    result = OfflineAuthentication.authenticate(make_account(username="  Steve  "))

    assert result.player_name == "Steve"
    assert result.uuid == OfflineAuthentication.uuid_generator("Steve").replace("-", "")


def test_authenticate_rejects_empty_username():
    with pytest.raises(ValueError, match="username"):
        OfflineAuthentication.authenticate(make_account(username="   "))


def test_authenticate_does_not_modify_account():
    account = make_account(
        username="Alex",
        player_uuid="aaaaaaaa-aaaa-3aaa-8aaa-aaaaaaaaaaaa",
    )
    original = (
        account.account_id,
        account.account_type,
        account.username,
        account.uuid,
        account.access_token,
        account.refresh_token,
        account.token_expires_at,
    )

    OfflineAuthentication.authenticate(account)

    assert (
        account.account_id,
        account.account_type,
        account.username,
        account.uuid,
        account.access_token,
        account.refresh_token,
        account.token_expires_at,
    ) == original


def test_uuid_generator_returns_valid_uuid():
    generated = OfflineAuthentication.uuid_generator(
        "Steve"
    )

    parsed = uuid.UUID(generated)

    assert str(parsed) == generated


def test_uuid_generator_creates_version_3_uuid():
    generated = uuid.UUID(
        OfflineAuthentication.uuid_generator(
            "Steve"
        )
    )

    assert generated.version == 3


def test_uuid_generator_uses_rfc_4122_variant():
    generated = uuid.UUID(
        OfflineAuthentication.uuid_generator(
            "Steve"
        )
    )

    assert generated.variant == uuid.RFC_4122


@pytest.mark.parametrize(
    (
        "username",
        "expected",
    ),
    [
        (
            "Steve",
            "5627dd98-e6be-3c21-b8a8-e92344183641",
        ),
        (
            "Alex",
            "36532b5e-c442-3dbb-a24c-c7e55d0f979a",
        ),
        (
            "Notch",
            "b50ad385-829d-3141-a216-7e7d7539ba7f",
        ),
    ],
)
def test_uuid_generator_matches_minecraft_offline_uuid_algorithm(
    username: str,
    expected: str,
):
    assert (
        OfflineAuthentication.uuid_generator(
            username
        )
        == expected
    )


def test_uuid_generator_is_deterministic():
    first = OfflineAuthentication.uuid_generator(
        "SamePlayer"
    )
    second = OfflineAuthentication.uuid_generator(
        "SamePlayer"
    )

    assert first == second


def test_uuid_generator_is_case_sensitive():
    lowercase = OfflineAuthentication.uuid_generator(
        "steve"
    )
    uppercase = OfflineAuthentication.uuid_generator(
        "Steve"
    )

    assert lowercase != uppercase


def test_uuid_generator_changes_for_different_names():
    first = OfflineAuthentication.uuid_generator(
        "PlayerOne"
    )
    second = OfflineAuthentication.uuid_generator(
        "PlayerTwo"
    )

    assert first != second


def test_uuid_generator_supports_unicode_names():
    generated = OfflineAuthentication.uuid_generator(
        "Mahiru雪"
    )

    parsed = uuid.UUID(generated)

    assert parsed.version == 3
    assert parsed.variant == uuid.RFC_4122


def test_uuid_generator_supports_empty_name():
    generated = OfflineAuthentication.uuid_generator(
        ""
    )

    parsed = uuid.UUID(generated)

    assert parsed.version == 3
    assert str(parsed) == generated


def test_authentication_model_uses_slots():
    authentication = OfflineAuthentication.authenticate(
        make_account()
    )

    with pytest.raises(AttributeError):
        authentication.extra_field = "not allowed"