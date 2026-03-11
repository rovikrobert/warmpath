"""Tests for report dedup, noise filtering, and stub overwrite protection."""

import json
from unittest.mock import patch

from agents.shared.report import AgentReport, Finding, merge_reports


# ---------------------------------------------------------------------------
# merge_reports dedup uses finding.id as primary key
# ---------------------------------------------------------------------------


class TestMergeReportsDedup:
    def test_dedup_by_finding_id(self):
        """Findings with the same id are merged, keeping higher severity."""
        r1 = AgentReport(
            agent="a",
            findings=[
                Finding(
                    id="SEC-001",
                    severity="medium",
                    category="security",
                    title="Issue A",
                    detail="d1",
                ),
            ],
        )
        r2 = AgentReport(
            agent="b",
            findings=[
                Finding(
                    id="SEC-001",
                    severity="high",
                    category="security",
                    title="Issue A",
                    detail="d2",
                ),
            ],
        )
        merged = merge_reports([r1, r2], skip_resolved=False)
        assert len(merged) == 1
        assert merged[0].severity == "high"
        assert merged[0].recurrence_count == 2

    def test_distinct_ids_not_merged(self):
        """Findings with different ids are kept separate even if same category."""
        r = AgentReport(
            agent="a",
            findings=[
                Finding(
                    id="DEP-A",
                    severity="low",
                    category="dependency-update",
                    title="Update A",
                    detail="d",
                    file=None,
                    line=None,
                ),
                Finding(
                    id="DEP-B",
                    severity="low",
                    category="dependency-update",
                    title="Update B",
                    detail="d",
                    file=None,
                    line=None,
                ),
            ],
        )
        merged = merge_reports([r], skip_resolved=False)
        assert len(merged) == 2

    def test_resolved_findings_skipped(self):
        """Findings in the resolved registry are filtered out."""
        r = AgentReport(
            agent="a",
            findings=[
                Finding(
                    id="RESOLVED-ONE",
                    severity="medium",
                    category="lint",
                    title="Resolved",
                    detail="d",
                ),
                Finding(
                    id="KEPT",
                    severity="medium",
                    category="lint",
                    title="Kept",
                    detail="d",
                ),
            ],
        )
        fake_registry = {
            "RESOLVED-ONE": {
                "resolution_type": "false_positive",
                "resolved_at": "2026-01-01T00:00:00+00:00",
                "reason": "test",
                "skip_until": None,
            }
        }
        with patch(
            "agents.shared.learning._load_resolved_registry", return_value=fake_registry
        ):
            merged = merge_reports([r], skip_resolved=True)
        ids = [f.id for f in merged]
        assert "RESOLVED-ONE" not in ids
        assert "KEPT" in ids


# ---------------------------------------------------------------------------
# Stub overwrite protection (lead save_report)
# ---------------------------------------------------------------------------


class TestStubOverwriteProtection:
    def test_stub_does_not_overwrite_real_report(self, tmp_path):
        """save_report refuses to overwrite a real report with a stub."""
        from agents.lead.lead import save_report

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()

        # Write a real report first
        real = AgentReport(
            agent="architect",
            scan_duration_seconds=5.2,
            findings=[
                Finding(
                    id="F1",
                    severity="high",
                    category="lint",
                    title="Real finding",
                    detail="d",
                ),
                Finding(
                    id="F2",
                    severity="low",
                    category="lint",
                    title="Another",
                    detail="d",
                ),
            ],
            metrics={"coverage": 85},
        )
        real_path = reports_dir / "architect_latest.json"
        real_path.write_text(real.serialize())

        # Try to overwrite with a stub
        stub = AgentReport(
            agent="architect",
            scan_duration_seconds=0,
            findings=[
                Finding(
                    id="f1",
                    severity="medium",
                    category="lint",
                    title="Unused import",
                    detail="d",
                ),
            ],
        )

        with patch("agents.lead.lead.REPORTS_DIR", reports_dir):
            save_report(stub)

        # Verify the real report was preserved
        saved = json.loads(real_path.read_text())
        assert saved["scan_duration_seconds"] == 5.2
        assert len(saved["findings"]) == 2

    def test_stub_can_write_when_no_existing_report(self, tmp_path):
        """save_report allows stubs when no existing report exists."""
        from agents.lead.lead import save_report

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()

        stub = AgentReport(
            agent="newagent",
            scan_duration_seconds=0,
            findings=[
                Finding(
                    id="f1",
                    severity="medium",
                    category="lint",
                    title="Finding",
                    detail="d",
                ),
            ],
        )
        with patch("agents.lead.lead.REPORTS_DIR", reports_dir):
            save_report(stub)

        path = reports_dir / "newagent_latest.json"
        assert path.exists()

    def test_real_report_overwrites_real_report(self, tmp_path):
        """save_report allows real reports to overwrite real reports."""
        from agents.lead.lead import save_report

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()

        old = AgentReport(
            agent="architect",
            scan_duration_seconds=3.0,
            findings=[
                Finding(
                    id="F1", severity="low", category="lint", title="Old", detail="d"
                ),
            ],
            metrics={"old": True},
        )
        real_path = reports_dir / "architect_latest.json"
        real_path.write_text(old.serialize())

        new = AgentReport(
            agent="architect",
            scan_duration_seconds=4.5,
            findings=[
                Finding(
                    id="F1", severity="medium", category="lint", title="New", detail="d"
                ),
                Finding(
                    id="F2", severity="low", category="lint", title="Extra", detail="d"
                ),
            ],
            metrics={"new": True},
        )
        with patch("agents.lead.lead.REPORTS_DIR", reports_dir):
            save_report(new)

        saved = json.loads(real_path.read_text())
        assert saved["scan_duration_seconds"] == 4.5
        assert saved["metrics"]["new"] is True


# ---------------------------------------------------------------------------
# Stub overwrite protection (TeamRunner._save_report)
# ---------------------------------------------------------------------------


class TestTeamRunnerStubGuard:
    def test_team_runner_refuses_stub_overwrite(self, tmp_path):
        """TeamRunner._save_report refuses to overwrite real with stub."""
        from app.agent_runtime.teams.base import TeamRunner, _TEAM_REPORTS_DIRS

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        _TEAM_REPORTS_DIRS["test_team"] = reports_dir

        # Write real report
        real_path = reports_dir / "testbot_latest.json"
        real_data = {
            "agent": "testbot",
            "scan_duration_seconds": 8.0,
            "findings": [
                {
                    "id": "F1",
                    "severity": "high",
                    "category": "sec",
                    "title": "Real",
                    "detail": "d",
                },
                {
                    "id": "F2",
                    "severity": "low",
                    "category": "sec",
                    "title": "Also real",
                    "detail": "d",
                },
            ],
            "metrics": {"x": 1},
        }
        real_path.write_text(json.dumps(real_data))

        runner = TeamRunner()
        runner.team_name = "test_team"

        stub = AgentReport(
            agent="testbot",
            scan_duration_seconds=0,
            findings=[
                Finding(
                    id="f1",
                    severity="medium",
                    category="lint",
                    title="Stub",
                    detail="d",
                ),
            ],
        )
        runner._save_report(stub)

        # Real report preserved
        saved = json.loads(real_path.read_text())
        assert saved["scan_duration_seconds"] == 8.0

        # Cleanup
        _TEAM_REPORTS_DIRS.pop("test_team", None)


# ---------------------------------------------------------------------------
# Redis report store stub guard
# ---------------------------------------------------------------------------


class TestRedisReportStoreStubGuard:
    def test_publish_report_refuses_stub_over_real(self):
        """publish_report refuses to overwrite a real Redis report with a stub."""
        from agents.shared.report_store import publish_report

        real_data = json.dumps(
            {
                "agent": "pipeline",
                "scan_duration_seconds": 5.0,
                "findings": [
                    {
                        "id": "F1",
                        "severity": "high",
                        "category": "data",
                        "title": "Real",
                        "detail": "d",
                    },
                    {
                        "id": "F2",
                        "severity": "low",
                        "category": "data",
                        "title": "Also real",
                        "detail": "d",
                    },
                ],
                "metrics": {"rows": 100},
            }
        )

        stub_data = json.dumps(
            {
                "agent": "pipeline",
                "scan_duration_seconds": 0,
                "findings": [
                    {
                        "id": "f1",
                        "severity": "medium",
                        "category": "data",
                        "title": "Stub",
                        "detail": "d",
                    },
                ],
                "metrics": {},
            }
        )

        class FakeRedis:
            def __init__(self):
                self.store = {"scan_report:data:pipeline_latest": real_data}

            def ping(self):
                pass

            def get(self, key):
                return self.store.get(key)

            def set(self, key, value, ex=None):
                self.store[key] = value

        fake = FakeRedis()

        with patch("agents.shared.report_store._get_sync_redis", return_value=fake):
            result = publish_report("data", "pipeline", stub_data)

        assert result is False
        # Real data should still be there
        saved = json.loads(fake.store["scan_report:data:pipeline_latest"])
        assert saved["scan_duration_seconds"] == 5.0


# ---------------------------------------------------------------------------
# Noise category filtering in synthesizer
# ---------------------------------------------------------------------------


class TestSynthesizerNoiseFiltering:
    def test_dependency_update_findings_excluded_from_brief(self):
        """Low/medium dependency-update findings should not appear in daily brief."""
        from agents.chief_of_staff.synthesizer import synthesize_daily

        reports = [
            AgentReport(
                agent="deps_manager",
                scan_duration_seconds=5.0,
                findings=[
                    Finding(
                        id="DEP-1",
                        severity="low",
                        category="dependency-update",
                        title="Update fastapi",
                        detail="0.109 -> 0.135",
                    ),
                    Finding(
                        id="DEP-2",
                        severity="medium",
                        category="dependency-update",
                        title="Major update redis",
                        detail="5 -> 7",
                    ),
                    Finding(
                        id="DEP-3",
                        severity="low",
                        category="dependency-dead",
                        title="Dead dep: fakeredis",
                        detail="Not imported",
                    ),
                    Finding(
                        id="DEP-4",
                        severity="medium",
                        category="dependency-missing",
                        title="Missing dep: google",
                        detail="Imported but not declared",
                    ),
                    Finding(
                        id="REAL-1",
                        severity="medium",
                        category="security",
                        title="SQL injection risk",
                        detail="Found in query",
                    ),
                ],
            ),
        ]

        _brief_text, brief_data = synthesize_daily(reports)

        # The real finding should be in key_updates
        update_ids = [u["id"] for u in brief_data.get("key_updates", [])]
        assert "REAL-1" in update_ids

        # Dep noise should NOT be in key_updates or decisions_needed
        decision_ids = [d["id"] for d in brief_data.get("decisions_needed", [])]
        all_surfaced = update_ids + decision_ids
        assert "DEP-1" not in all_surfaced
        assert "DEP-2" not in all_surfaced
        assert "DEP-3" not in all_surfaced
        assert "DEP-4" not in all_surfaced

    def test_critical_dependency_finding_still_surfaces(self):
        """Critical/high dependency findings should still appear."""
        from agents.chief_of_staff.synthesizer import synthesize_daily

        reports = [
            AgentReport(
                agent="deps_manager",
                scan_duration_seconds=5.0,
                findings=[
                    Finding(
                        id="DEP-CVE",
                        severity="critical",
                        category="dependency-update",
                        title="CVE in openssl",
                        detail="Active exploit",
                    ),
                ],
            ),
        ]

        _brief_text, brief_data = synthesize_daily(reports)

        decision_ids = [d["id"] for d in brief_data.get("decisions_needed", [])]
        assert "DEP-CVE" in decision_ids
