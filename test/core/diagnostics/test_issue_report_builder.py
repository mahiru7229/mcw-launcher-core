from pathlib import Path
from urllib.parse import parse_qs, urlparse

from src.core.diagnostics.issue_report_builder import IssueReportBuilder


def test_issue_report_builder_redacts_and_includes_diagnostics_filename() -> None:
    details = {
        "title": "Launch failed",
        "what_happened": "Authorization: Bearer secret-token",
        "steps": "1. Launch instance",
        "expected": "Game opens",
        "actual": "Launcher reports an error",
        "context": "instance=RLCraft",
    }
    body = IssueReportBuilder.build_body(
        details,
        launcher_version="1.4.0-beta.4",
        diagnostics_path=Path("MCW-Diagnostics-20260812-190000.zip"),
    )

    assert "MCW-Diagnostics-20260812-190000.zip" in body
    assert "1.4.0-beta.4" in body
    assert "secret-token" not in body
    assert "<redacted>" in body


def test_github_new_issue_url_prefills_title_and_body() -> None:
    url = IssueReportBuilder.github_new_issue_url(
        "mahiru7229/mcw-launcher",
        {"title": "Forge profile issue", "what_happened": "Forge failed"},
        launcher_version="1.4.0-beta.4",
    )
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert parsed.netloc == "github.com"
    assert parsed.path == "/mahiru7229/mcw-launcher/issues/new"
    assert query["title"] == ["Forge profile issue"]
    assert "Forge failed" in query["body"][0]


def test_issue_report_builder_hides_drive_letters() -> None:
    body = IssueReportBuilder.build_body(
        {"title": "Path error", "what_happened": r"Failed at D:\\Games\\MCW\\instances\\Pack\\file.jar"},
        launcher_version="1.4.1-beta.1",
    )

    assert "D:" not in body
    assert "root/Games/MCW/instances/Pack/file.jar" in body
