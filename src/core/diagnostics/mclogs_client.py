from __future__ import annotations

from typing import Any
import httpx

from src.core.security.sensitive_data_redactor import SensitiveDataRedactor

MCLOGS_API_URL = "https://api.mclo.gs/1/log"
MAX_LOG_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


class McLogsClientError(RuntimeError):
    """Raised when log upload to mclo.gs fails."""


class McLogsClient:
    """Client for uploading sanitized logs to the mclo.gs paste service."""

    @staticmethod
    def upload(content: str, timeout: float = 15.0) -> dict[str, Any]:
        """Upload raw log text to mclo.gs and return the response metadata.

        The log text is automatically sanitized to redact sensitive tokens,
        emails, and OS paths with personal usernames.
        """
        raw_text = str(content or "").strip()
        if not raw_text:
            raise McLogsClientError("Log content is empty.")

        sanitized_text = SensitiveDataRedactor.redact_text(raw_text)
        payload_bytes = sanitized_text.encode("utf-8")
        if len(payload_bytes) > MAX_LOG_SIZE_BYTES:
            # Truncate oldest lines to fit within size limit while preserving the crash end
            lines = sanitized_text.splitlines()
            truncated = []
            current_size = 0
            for line in reversed(lines):
                line_size = len(line.encode("utf-8")) + 1
                if current_size + line_size > MAX_LOG_SIZE_BYTES - 1024:
                    break
                truncated.append(line)
                current_size += line_size
            sanitized_text = "[... truncated earlier log lines ...]\n" + "\n".join(reversed(truncated))

        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    MCLOGS_API_URL,
                    data={"content": sanitized_text},
                    headers={"User-Agent": "MCW-Launcher/1.6"},
                )
                response.raise_for_status()
                data = response.json()
        except Exception as error:
            raise McLogsClientError(f"Failed to upload log to mclo.gs: {error}") from error

        if not isinstance(data, dict) or not data.get("success"):
            error_msg = data.get("error", "Unknown mclo.gs API error") if isinstance(data, dict) else "Invalid API response"
            raise McLogsClientError(f"mclo.gs error: {error_msg}")

        return {
            "success": True,
            "id": str(data.get("id") or ""),
            "url": str(data.get("url") or ""),
            "raw": str(data.get("raw") or ""),
        }
