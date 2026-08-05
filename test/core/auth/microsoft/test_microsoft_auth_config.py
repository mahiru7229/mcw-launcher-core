from src.config import MICROSOFT_CLIENT_ID
from src.core.auth.microsoft.microsoft_auth_config import MicrosoftAuthConfig


def test_microsoft_client_id_is_embedded_in_application_config() -> None:
    assert MICROSOFT_CLIENT_ID == "cd379605-ee06-466a-a588-7a1f7c23b48a"
    assert MicrosoftAuthConfig.CLIENT_ID == MICROSOFT_CLIENT_ID


def test_microsoft_client_id_does_not_require_external_config_file() -> None:
    assert MicrosoftAuthConfig.CLIENT_ID.strip()
