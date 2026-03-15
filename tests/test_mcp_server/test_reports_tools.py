"""Tests for MCP agent report tools."""

from __futu[RESEND_KEY_REDACTED] import annotations

from pathlib import Path
from unittest.mock import patch

from mcp_server.tools.reports import list_reports, read_report


class TestListReports:
    def test_returns_reports_from_teams(self, tmp_path: Path) -> None:
        for team in ["agents", "data_team", "product_team"]:
            team_dir = tmp_path / team / "reports"
            team_dir.mkdir(parents=True)
            (team_dir / f"{team}_latest.json").write_text('{"test": true}')

        with patch(
            "mcp_server.tools.reports._get_project_root", return_value=str(tmp_path)
        ):
            result = list_reports()
            assert len(result["reports"]) >= 3

    def test_returns_empty_when_no_reports(self, tmp_path: Path) -> None:
        with patch(
            "mcp_server.tools.reports._get_project_root", return_value=str(tmp_path)
        ):
            result = list_reports()
            assert result["reports"] == []


class TestReadReport:
    def test_reads_existing_report(self, tmp_path: Path) -> None:
        report_dir = tmp_path / "agents" / "reports"
        report_dir.mkdir(parents=True)
        (report_dir / "test_report.json").write_text('{"finding": "all good"}')

        with patch(
            "mcp_server.tools.reports._get_project_root", return_value=str(tmp_path)
        ):
            result = read_report(team="agents", filename="test_report.json")
            assert result["content"] == '{"finding": "all good"}'

    def test_nonexistent_report_returns_error(self, tmp_path: Path) -> None:
        with patch(
            "mcp_server.tools.reports._get_project_root", return_value=str(tmp_path)
        ):
            result = read_report(team="agents", filename="nope.json")
            assert "error" in result

    def test_path_traversal_blocked(self, tmp_path: Path) -> None:
        with patch(
            "mcp_server.tools.reports._get_project_root", return_value=str(tmp_path)
        ):
            result = read_report(team="agents", filename="../../etc/passwd")
            assert "error" in result


class TestListReportsSubdirectories:
    def test_includes_reports_from_subdirectories(self, tmp_path: Path) -> None:
        """Telegram reports in telegram/ subdirectory should appear in listing."""
        cos_dir = tmp_path / "agents" / "chief_of_staff" / "reports"
        cos_dir.mkdir(parents=True)
        (cos_dir / "daily-2026-03-15.md").write_text("top-level report")

        telegram_dir = cos_dir / "telegram"
        telegram_dir.mkdir()
        (telegram_dir / "daily-brief-2026-03-15.md").write_text("telegram report")

        with patch(
            "mcp_server.tools.reports._get_project_root", return_value=str(tmp_path)
        ):
            result = list_reports()
            filenames = [r["filename"] for r in result["reports"]]
            assert "daily-2026-03-15.md" in filenames
            assert "telegram/daily-brief-2026-03-15.md" in filenames
            assert result["count"] == 2


class TestReadReportSubdirectories:
    def test_reads_report_from_subdirectory(self, tmp_path: Path) -> None:
        """read_report should accept subdirectory paths like telegram/foo.md."""
        telegram_dir = tmp_path / "agents" / "chief_of_staff" / "reports" / "telegram"
        telegram_dir.mkdir(parents=True)
        (telegram_dir / "daily-brief.md").write_text("telegram content")

        with patch(
            "mcp_server.tools.reports._get_project_root", return_value=str(tmp_path)
        ):
            result = read_report(
                team="agents/chief_of_staff",
                filename="telegram/daily-brief.md",
            )
            assert result["content"] == "telegram content"
            assert result["filename"] == "telegram/daily-brief.md"

    def test_subdirectory_path_traversal_still_blocked(self, tmp_path: Path) -> None:
        with patch(
            "mcp_server.tools.reports._get_project_root", return_value=str(tmp_path)
        ):
            result = read_report(
                team="agents/chief_of_staff",
                filename="telegram/../../etc/passwd",
            )
            assert "error" in result


class TestReadReportInvalidTeam:
    def test_unknown_team_returns_error(self, tmp_path: Path) -> None:
        with patch(
            "mcp_server.tools.reports._get_project_root", return_value=str(tmp_path)
        ):
            result = read_report(team="nonexistent_team", filename="report.json")
            assert "error" in result
