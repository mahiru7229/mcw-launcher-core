import base64
import hashlib
import secrets


class PKCE:

    @staticmethod
    def generate_verifier() -> str:
        return secrets.token_urlsafe(64)

    @staticmethod
    def create_challenge(verifier: str) -> str:
        digest = hashlib.sha256(verifier.encode("ascii")).digest()

        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")