from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Event
from time import monotonic
from urllib.parse import parse_qs, urlparse


class MicrosoftAuthorizationCancelledError(RuntimeError):
    pass


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    authorization_code: str | None = None
    returned_state: str | None = None
    error: str | None = None
    error_description: str | None = None

    def do_GET(self) -> None:
        query = parse_qs(urlparse(self.path).query)

        OAuthCallbackHandler.authorization_code = query.get("code", [None])[0]
        OAuthCallbackHandler.returned_state = query.get("state", [None])[0]
        OAuthCallbackHandler.error = query.get("error", [None])[0]
        OAuthCallbackHandler.error_description = query.get("error_description", [None])[0]

        if OAuthCallbackHandler.authorization_code:
            message = """
            <html>
                <head>
                    <meta charset="UTF-8">
                    <title>MCW Launcher</title>
                </head>
                <body>
                    <h2>Microsoft login completed.</h2>
                    <p>You can close this window and return to MCW Launcher.</p>
                </body>
            </html>
            """
            status = 200
        else:
            message = """
            <html>
                <head>
                    <meta charset="UTF-8">
                    <title>MCW Launcher</title>
                </head>
                <body>
                    <h2>Microsoft login failed.</h2>
                    <p>You can close this window and return to MCW Launcher.</p>
                </body>
            </html>
            """
            status = 400

        body = message.encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Security-Policy", "default-src 'none'")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        pass


class ReusableOAuthHTTPServer(HTTPServer):
    allow_reuse_address = True


class OAuthCallbackServer:
    POLL_INTERVAL_SECONDS = 0.25

    @staticmethod
    def wait_for_callback(timeout: float = 180.0, cancel_event: Event | None = None) -> tuple[str, str]:
        OAuthCallbackHandler.authorization_code = None
        OAuthCallbackHandler.returned_state = None
        OAuthCallbackHandler.error = None
        OAuthCallbackHandler.error_description = None

        server = ReusableOAuthHTTPServer(("localhost", 8400), OAuthCallbackHandler)
        server.timeout = OAuthCallbackServer.POLL_INTERVAL_SECONDS
        deadline = monotonic() + max(0.0, float(timeout))

        try:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise MicrosoftAuthorizationCancelledError("Microsoft sign-in was cancelled.")

                if monotonic() >= deadline:
                    raise TimeoutError("Microsoft authorization callback was not received.")

                server.handle_request()

                if OAuthCallbackHandler.authorization_code or OAuthCallbackHandler.error:
                    break
        finally:
            server.server_close()

        authorization_code = OAuthCallbackHandler.authorization_code
        returned_state = OAuthCallbackHandler.returned_state
        callback_error = OAuthCallbackHandler.error
        error_description = OAuthCallbackHandler.error_description
        OAuthCallbackHandler.authorization_code = None
        OAuthCallbackHandler.returned_state = None
        OAuthCallbackHandler.error = None
        OAuthCallbackHandler.error_description = None

        if callback_error:
            if callback_error == "access_denied":
                raise MicrosoftAuthorizationCancelledError("Microsoft sign-in was cancelled.")
            detail = f": {error_description}" if error_description else ""
            raise RuntimeError(f"Microsoft authorization failed: {callback_error}{detail}")

        if not authorization_code:
            raise TimeoutError("Microsoft authorization callback was not received.")

        if not returned_state:
            raise RuntimeError("Microsoft authorization callback did not contain state.")

        return authorization_code, returned_state
