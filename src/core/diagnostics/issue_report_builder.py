from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from src.core.security.sensitive_data_redactor import SensitiveDataRedactor


class IssueReportBuilder:
    """Build a privacy-filtered GitHub issue draft from user-provided context."""

    @staticmethod
    def normalize(details: dict[str, Any]) -> dict[str, str]:
        fields = ("title", "what_happened", "steps", "expected", "actual", "context")
        return {
            field: SensitiveDataRedactor.redact_text(str(details.get(field) or "").strip())
            for field in fields
        }

    @classmethod
    def build_body(cls, details: dict[str, Any], *, launcher_version: str, diagnostics_path: Path | None = None) -> str:
        safe = cls.normalize(details)
        diagnostics_name = Path(diagnostics_path).name if diagnostics_path is not None else "MCW-Diagnostics-YYYYMMDD-HHMMSS.zip"
        lines = [
            "## What happened",
            safe["what_happened"] or "(please describe the problem)",
            "",
            "## Steps to reproduce",
            safe["steps"] or "1. ",
            "",
            "## Expected behavior",
            safe["expected"] or "(what did you expect to happen?)",
            "",
            "## Actual behavior",
            safe["actual"] or "(what happened instead?)",
            "",
            "## Launcher context",
            f"- MCW Launcher: {launcher_version}",
        ]
        if safe["context"]:
            lines.append(f"- Context: {safe['context']}")
        lines.extend(
            [
                "",
                "## Diagnostics",
                f"Attach `{diagnostics_name}` to this issue by dragging the ZIP into the GitHub issue editor.",
                "",
                "> The diagnostic bundle is privacy-filtered, but you should still review the issue text and attachments before submitting.",
            ]
        )
        return "\n".join(lines).rstrip() + "\n"

    @classmethod
    def github_new_issue_url(cls, repository: str, details: dict[str, Any], *, launcher_version: str, diagnostics_path: Path | None = None) -> str:
        repo = str(repository or "").strip().strip("/")
        if not repo or "/" not in repo:
            raise ValueError("A GitHub owner/repository name is required.")
        safe = cls.normalize(details)
        title = safe["title"] or f"Bug report - MCW Launcher {launcher_version}"
        body = cls.build_body(details, launcher_version=launcher_version, diagnostics_path=diagnostics_path)
        return f"https://github.com/{repo}/issues/new?{urlencode({'title': title, 'body': body})}"
