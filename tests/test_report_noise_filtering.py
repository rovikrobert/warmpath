"""Tests for report dedup, noise filtering, and stub overwrite protection."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from agents.shared.learning import filter_resolved_findings
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


# ---------------------------------------------------------------------------
# filter_resolved_findings — prefix matching, edge cases, skip_until expiry
# ---------------------------------------------------------------------------


def _make_finding(**kwargs):
    defaults = dict(
        id="TEST-001",
        severity="medium",
        category="security",
        title="Test finding",
        detail="d",
    )
    defaults.update(kwargs)
    return Finding(**defaults)


def _fake_registry(entries: dict):
    return patch(
        "agents.shared.learning._load_resolved_registry",
        return_value=entries,
    )


class TestFilterResolvedFindings:
    def test_exact_match_filters_permanently_resolved(self):
        """Exact ID match with skip_until=None is permanently suppressed."""
        findings = [_make_finding(id="SEC-001")]
        reg = {
            "SEC-001": {
                "resolution_type": "false_positive",
                "resolved_at": "2026-01-01T00:00:00+00:00",
                "reason": "test",
                "skip_until": None,
            }
        }
        with _fake_registry(reg):
            result = filter_resolved_findings(findings)
        assert len(result) == 0

    def test_exact_match_filters_within_skip_window(self):
        """Finding within skip_until window is suppressed."""
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        findings = [_make_finding(id="DEFER-001")]
        reg = {
            "DEFER-001": {
                "resolution_type": "deferred",
                "resolved_at": "2026-01-01T00:00:00+00:00",
                "reason": "test",
                "skip_until": future,
            }
        }
        with _fake_registry(reg):
            result = filter_resolved_findings(findings)
        assert len(result) == 0

    def test_expired_skip_window_resurfaces_finding(self):
        """Finding past skip_until window reappears."""
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        findings = [_make_finding(id="DEFER-002")]
        reg = {
            "DEFER-002": {
                "resolution_type": "deferred",
                "resolved_at": "2026-01-01T00:00:00+00:00",
                "reason": "test",
                "skip_until": past,
            }
        }
        with _fake_registry(reg):
            result = filter_resolved_findings(findings)
        assert len(result) == 1
        assert result[0].id == "DEFER-002"

    def test_prefix_match_finding_extends_registry_key_within_overlap(self):
        """Finding 'SEC-001-v2' matches registry 'SEC-001' when overlap >= 50%."""
        findings = [_make_finding(id="SEC-001-v2")]
        reg = {
            "SEC-001": {
                "resolution_type": "false_positive",
                "resolved_at": "2026-01-01T00:00:00+00:00",
                "reason": "test",
                "skip_until": None,
            }
        }
        with _fake_registry(reg):
            result = filter_resolved_findings(findings)
        # SEC-001 (7) vs SEC-001-v2 (10): 7/10=70% >= 50% → matches
        assert len(result) == 0

    def test_prefix_match_rejects_low_overlap(self):
        """Finding 'SEC-001-very-long-extra-detail' does NOT match 'SEC-001'."""
        findings = [_make_finding(id="SEC-001-very-long-extra-detail")]
        reg = {
            "SEC-001": {
                "resolution_type": "false_positive",
                "resolved_at": "2026-01-01T00:00:00+00:00",
                "reason": "test",
                "skip_until": None,
            }
        }
        with _fake_registry(reg):
            result = filter_resolved_findings(findings)
        # SEC-001 (7) vs 30 chars: 7/30=23% < 50% → no match
        assert len(result) == 1

    def test_prefix_match_registry_extends_finding(self):
        """Registry key 'lc-sec-token_versio' matches finding 'lc-sec-token_vers'."""
        findings = [_make_finding(id="lc-sec-token_vers")]
        reg = {
            "lc-sec-token_versio": {
                "resolution_type": "false_positive",
                "resolved_at": "2026-01-01T00:00:00+00:00",
                "reason": "test",
                "skip_until": None,
            }
        }
        with _fake_registry(reg):
            result = filter_resolved_findings(findings)
        assert len(result) == 0

    def test_short_prefix_does_not_match_long_id(self):
        """Short prefix 'SEC' must NOT match 'SEC-AUTH-COVERAGE-app-...'."""
        findings = [_make_finding(id="SEC")]
        reg = {
            "SEC-AUTH-COVERAGE-app-api-agents.py:304": {
                "resolution_type": "false_positive",
                "resolved_at": "2026-01-01T00:00:00+00:00",
                "reason": "test",
                "skip_until": None,
            }
        }
        with _fake_registry(reg):
            result = filter_resolved_findings(findings)
        # 'SEC' is too short (3 chars) relative to the registry key (43 chars)
        assert len(result) == 1

    def test_similar_line_numbers_do_not_cross_match(self):
        """Findings at :304 and :338 must not cross-match each other."""
        findings = [
            _make_finding(id="SEC-AUTH-COVERAGE-app-api-agents.py:338"),
        ]
        reg = {
            "SEC-AUTH-COVERAGE-app-api-agents.py:304": {
                "resolution_type": "false_positive",
                "resolved_at": "2026-01-01T00:00:00+00:00",
                "reason": "test",
                "skip_until": None,
            }
        }
        with _fake_registry(reg):
            result = filter_resolved_findings(findings)
        # :338 is NOT a prefix of :304 and vice versa — must NOT match
        assert len(result) == 1
        assert result[0].id == "SEC-AUTH-COVERAGE-app-api-agents.py:338"

    def test_empty_id_finding_is_kept(self):
        """Finding with empty string ID should not match any registry entry."""
        findings = [_make_finding(id="")]
        reg = {
            "SEC-001": {
                "resolution_type": "false_positive",
                "resolved_at": "2026-01-01T00:00:00+00:00",
                "reason": "test",
                "skip_until": None,
            }
        }
        with _fake_registry(reg):
            result = filter_resolved_findings(findings)
        assert len(result) == 1

    def test_dict_finding_without_id_is_kept(self):
        """Dict finding with missing 'id' key should not crash or be filtered."""
        findings = [{"severity": "medium", "title": "No id"}]
        reg = {
            "X": {
                "resolution_type": "false_positive",
                "resolved_at": "2026-01-01T00:00:00+00:00",
                "reason": "test",
                "skip_until": None,
            }
        }
        with _fake_registry(reg):
            result = filter_resolved_findings(findings)
        assert len(result) == 1

    def test_dict_finding_with_none_id_is_kept(self):
        """Dict finding with id=None should not crash or be filtered."""
        findings = [{"id": None, "severity": "medium", "title": "None id"}]
        reg = {
            "X": {
                "resolution_type": "false_positive",
                "resolved_at": "2026-01-01T00:00:00+00:00",
                "reason": "test",
                "skip_until": None,
            }
        }
        with _fake_registry(reg):
            result = filter_resolved_findings(findings)
        assert len(result) == 1

    def test_empty_registry_keeps_all_findings(self):
        """Empty registry returns all findings unchanged."""
        findings = [_make_finding(id="A"), _make_finding(id="B")]
        with _fake_registry({}):
            result = filter_resolved_findings(findings)
        assert len(result) == 2

    def test_unresolved_finding_kept_alongside_resolved(self):
        """Only the resolved finding is filtered; others stay."""
        findings = [
            _make_finding(id="RESOLVED"),
            _make_finding(id="KEPT"),
        ]
        reg = {
            "RESOLVED": {
                "resolution_type": "fixed",
                "resolved_at": "2026-01-01T00:00:00+00:00",
                "reason": "test",
                "skip_until": "2099-01-01",
            }
        }
        with _fake_registry(reg):
            result = filter_resolved_findings(findings)
        assert len(result) == 1
        assert result[0].id == "KEPT"


class TestSynthesizerCategorySuppression:
    """Category-level suppression filters out known false-positive-heavy categories."""

    def test_sql_injection_suppressed_unless_critical(self):
        """sql_injection findings below critical are suppressed."""
        from agents.chief_of_staff.synthesizer import synthesize_daily

        reports = [
            AgentReport(
                agent="security",
                scan_duration_seconds=5.0,
                findings=[
                    Finding(
                        id="SEC-SQLI-1",
                        severity="high",
                        category="sql_injection",
                        title="Possible SQL injection",
                        detail="f-string in execute()",
                    ),
                    Finding(
                        id="REAL-1",
                        severity="medium",
                        category="security",
                        title="Real security issue",
                        detail="Something real",
                    ),
                ],
            ),
        ]

        _brief, data = synthesize_daily(reports)

        all_ids = [d["id"] for d in data.get("decisions_needed", [])] + [
            u["id"] for u in data.get("key_updates", [])
        ]
        assert "SEC-SQLI-1" not in all_ids, "sql_injection high should be suppressed"
        assert "REAL-1" in all_ids, "real security finding should remain"

    def test_auth_coverage_suppressed_unless_critical(self):
        """auth_coverage findings below critical are suppressed."""
        from agents.chief_of_staff.synthesizer import synthesize_daily

        reports = [
            AgentReport(
                agent="security",
                scan_duration_seconds=5.0,
                findings=[
                    Finding(
                        id="SEC-AUTH-1",
                        severity="medium",
                        category="auth_coverage",
                        title="Endpoint missing auth",
                        detail="Scanner false positive",
                    ),
                ],
            ),
        ]

        _brief, data = synthesize_daily(reports)

        all_ids = [d["id"] for d in data.get("decisions_needed", [])] + [
            u["id"] for u in data.get("key_updates", [])
        ]
        assert "SEC-AUTH-1" not in all_ids

    def test_pii_leak_suppressed_unless_critical(self):
        """pii_leak findings below critical are suppressed."""
        from agents.chief_of_staff.synthesizer import synthesize_daily

        reports = [
            AgentReport(
                agent="privy",
                scan_duration_seconds=5.0,
                findings=[
                    Finding(
                        id="PRIV-PII-1",
                        severity="medium",
                        category="pii_leak",
                        title="PII in log",
                        detail="Logger has .email",
                    ),
                ],
            ),
        ]

        _brief, data = synthesize_daily(reports)

        all_ids = [d["id"] for d in data.get("decisions_needed", [])] + [
            u["id"] for u in data.get("key_updates", [])
        ]
        assert "PRIV-PII-1" not in all_ids

    def test_critical_suppressed_category_still_surfaces(self):
        """Critical findings in suppressed categories still surface."""
        from agents.chief_of_staff.synthesizer import synthesize_daily

        reports = [
            AgentReport(
                agent="security",
                scan_duration_seconds=5.0,
                findings=[
                    Finding(
                        id="SEC-SQLI-CRIT",
                        severity="critical",
                        category="sql_injection",
                        title="Real SQL injection",
                        detail="User input in query",
                    ),
                ],
            ),
        ]

        _brief, data = synthesize_daily(reports)

        decision_ids = [d["id"] for d in data.get("decisions_needed", [])]
        assert "SEC-SQLI-CRIT" in decision_ids

    def test_suppression_applied_to_weekly_synthesis(self):
        """Weekly synthesis also applies category suppression."""
        from agents.chief_of_staff.synthesizer import synthesize_weekly

        reports = [
            AgentReport(
                agent="security",
                scan_duration_seconds=5.0,
                findings=[
                    Finding(
                        id="SEC-AUTH-W",
                        severity="medium",
                        category="auth_coverage",
                        title="Endpoint missing auth",
                        detail="Scanner false positive",
                    ),
                ],
            ),
        ]

        text = synthesize_weekly(reports)

        # Suppressed category should not appear in weekly output
        assert "Endpoint missing auth" not in text

    def test_suppression_applied_to_status_synthesis(self):
        """Status synthesis also applies category suppression."""
        from agents.chief_of_staff.synthesizer import synthesize_status

        reports = [
            AgentReport(
                agent="security",
                scan_duration_seconds=5.0,
                findings=[
                    Finding(
                        id="SEC-PII-S",
                        severity="medium",
                        category="pii_leak",
                        title="PII in logs",
                        detail="Scanner FP",
                    ),
                ],
            ),
        ]

        text = synthesize_status(reports)

        # Finding count should be 0 after suppression
        assert "0 critical, 0 high" in text


class TestTeamSummariesExcludeFilteredFindings:
    """Team summaries and progress must not leak resolved or noisy findings."""

    def test_resolved_finding_excluded_from_team_summary_health(self):
        """A resolved high-severity finding must not make team health 'red'."""
        from agents.chief_of_staff.synthesizer import synthesize_daily

        reports = [
            AgentReport(
                agent="architect",
                scan_duration_seconds=5.0,
                findings=[
                    Finding(
                        id="RESOLVED-HIGH",
                        severity="high",
                        category="security",
                        title="Resolved security issue",
                        detail="In resolved registry",
                    ),
                ],
            ),
        ]

        fake_reg = {
            "RESOLVED-HIGH": {
                "resolution_type": "false_positive",
                "resolved_at": "2026-01-01T00:00:00+00:00",
                "reason": "test",
                "skip_until": None,
            }
        }
        with _fake_registry(fake_reg):
            _brief, data = synthesize_daily(reports)

        # Team summary should be green (no unresolved findings)
        eng_summary = next(
            (ts for ts in data["team_summaries"] if ts["team"] == "engineering"),
            None,
        )
        assert eng_summary is not None
        assert eng_summary["health"] == "green"
        assert eng_summary["finding_count"] == 0

    def test_noisy_category_excluded_from_team_summary_count(self):
        """Suppressed-category findings must not inflate team finding counts."""
        from agents.chief_of_staff.synthesizer import synthesize_daily

        reports = [
            AgentReport(
                agent="architect",
                scan_duration_seconds=5.0,
                findings=[
                    Finding(
                        id="SEC-AUTH-FP",
                        severity="high",
                        category="auth_coverage",
                        title="Endpoint missing auth",
                        detail="Scanner false positive",
                    ),
                    Finding(
                        id="SEC-SQLI-FP",
                        severity="medium",
                        category="sql_injection",
                        title="SQL injection in search",
                        detail="Parameterized query",
                    ),
                    Finding(
                        id="REAL-FINDING",
                        severity="low",
                        category="lint",
                        title="Real lint issue",
                        detail="Unused import",
                    ),
                ],
            ),
        ]

        with _fake_registry({}):
            _brief, data = synthesize_daily(reports)

        eng_summary = next(
            (ts for ts in data["team_summaries"] if ts["team"] == "engineering"),
            None,
        )
        assert eng_summary is not None
        # Only the real finding should count
        assert eng_summary["finding_count"] == 1
        assert eng_summary["health"] == "green"

    def test_resolved_finding_not_in_telegram_decisions(self):
        """Resolved findings must not appear in Telegram brief decisions."""
        from agents.chief_of_staff.synthesizer import synthesize_daily

        reports = [
            AgentReport(
                agent="security_scanner",
                scan_duration_seconds=5.0,
                findings=[
                    Finding(
                        id="SEC-DEPENDENCY-0",
                        severity="high",
                        category="dependency-vulnerability",
                        title="langchain-core CVE",
                        detail="Not exploitable",
                    ),
                    Finding(
                        id="SEC-AUTH-COVERAGE-app-api-credits.py:57",
                        severity="high",
                        category="auth_coverage",
                        title="Endpoint missing auth",
                        detail="Scanner FP",
                    ),
                ],
            ),
        ]

        fake_reg = {
            "SEC-DEPENDENCY-0": {
                "resolution_type": "deferred",
                "resolved_at": "2026-03-12T00:00:00+00:00",
                "reason": "Not exploitable",
                "skip_until": "2026-05-01",
            },
            "SEC-AUTH-COVERAGE-app-api-credits.py:57": {
                "resolution_type": "false_positive",
                "resolved_at": "2026-03-12T00:00:00+00:00",
                "reason": "Scanner FP",
                "skip_until": None,
            },
        }
        with _fake_registry(fake_reg):
            _brief, data = synthesize_daily(reports)

        decision_ids = [d["id"] for d in data.get("decisions_needed", [])]
        assert "SEC-DEPENDENCY-0" not in decision_ids
        assert "SEC-AUTH-COVERAGE-app-api-credits.py:57" not in decision_ids
        # Team summaries should also be clean
        for ts in data.get("team_summaries", []):
            assert ts["finding_count"] == 0


class TestSynthesizerSavesPendingDecisions:
    def test_daily_brief_saves_pending_decisions_for_critical_findings(self):
        """synthesize_daily persists pending decisions from critical/high findings."""
        from unittest.mock import patch as mock_patch

        from agents.chief_of_staff.synthesizer import synthesize_daily
        from agents.shared.decision_registry import load_pending_decisions

        reports = [
            AgentReport(
                agent="security_scanner",
                scan_duration_seconds=5.0,
                findings=[
                    Finding(
                        id="CVE-CRITICAL",
                        severity="critical",
                        category="dependency-vulnerability",
                        title="Critical CVE",
                        detail="Fix available",
                        recommendation="Bump foo>=2.0",
                        auto_fixable=True,
                        file="requirements.txt",
                    ),
                    Finding(
                        id="LOW-NOISE",
                        severity="low",
                        category="security",
                        title="Low finding",
                        detail="Not a decision",
                    ),
                ],
            ),
        ]

        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "pending_decisions.json"
            with (
                _fake_registry({}),
                mock_patch("agents.shared.decision_registry.DECISIONS_PATH", tmp_path),
            ):
                _brief, _data = synthesize_daily(reports)
                decisions = load_pending_decisions()

        # Only critical/high findings become pending decisions
        assert len(decisions) >= 1
        assert decisions[0].finding_id == "CVE-CRITICAL"
        # Original Finding fields preserved (not CosFinding)
        assert decisions[0].finding.get("auto_fixable") is True
        assert decisions[0].finding.get("file") == "requirements.txt"


# ---------------------------------------------------------------------------
# N+1 scanner: # n1-ok suppression and ID stability
# ---------------------------------------------------------------------------


class TestN1OkSuppression:
    """Verify that both N+1 scanners respect # n1-ok comments."""

    def test_perf_monitor_skips_n1_ok_lines(self, tmp_path):
        """perf_monitor _scan_n_plus_one ignores lines with # n1-ok."""
        from agents.perf_monitor.perf_monitor import _scan_n_plus_one

        # Create a fake app dir with a file containing n1-ok
        tasks_dir = tmp_path / "app" / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "__init__.py").touch()
        (tasks_dir / "example.py").write_text(
            "import ast\n"
            "async def batch_load(db):\n"
            "    while True:\n"
            "        result = await db.execute(query)  # n1-ok: batch pagination\n"
            "        if not result:\n"
            "            break\n"
        )
        # Also a file WITHOUT the comment (should be detected)
        (tasks_dir / "bad.py").write_text(
            "import ast\n"
            "async def loop_query(db):\n"
            "    for item in items:\n"
            "        result = await db.execute(query)\n"
        )

        with patch("agents.perf_monitor.perf_monitor.PROJECT_ROOT", tmp_path):
            findings, count = _scan_n_plus_one(tmp_path / "app")

        ids = [f.id for f in findings]
        # The n1-ok file should be suppressed
        assert not any("EXAMPLE" in fid for fid in ids), f"n1-ok not suppressed: {ids}"
        # The bad file should still be detected
        assert any("BAD" in fid for fid in ids), f"Bad file not detected: {ids}"
        assert count == 1

    def test_architect_skips_n1_ok_lines(self, tmp_path):
        """architect _scan_n_plus_one ignores lines with # n1-ok."""
        from agents.architect.architect import _scan_n_plus_one

        suppressed = tmp_path / "suppressed.py"
        suppressed.write_text(
            "async def batch(db):\n"
            "    while True:\n"
            "        r = await db.execute(q)  # n1-ok: intentional\n"
            "        if not r:\n"
            "            break\n"
        )
        detected = tmp_path / "detected.py"
        detected.write_text(
            "async def bad(db):\n    for x in items:\n        r = await db.execute(q)\n"
        )

        findings: list[Finding] = []
        _scan_n_plus_one([suppressed, detected], findings)

        ids = [f.id for f in findings]
        assert not any("SUPPRESSED" in fid for fid in ids), (
            f"n1-ok not suppressed: {ids}"
        )
        assert any("DETECTED" in fid for fid in ids), f"Bad file not detected: {ids}"


class TestArchitectN1IdStability:
    """Verify architect N+1 findings have unique, location-specific IDs."""

    def test_different_files_get_different_ids(self, tmp_path):
        """N+1 findings in different files get distinct IDs."""
        from agents.architect.architect import _scan_n_plus_one

        file_a = tmp_path / "alpha.py"
        file_a.write_text(
            "async def a(db):\n    for x in items:\n        r = await db.execute(q)\n"
        )
        file_b = tmp_path / "beta.py"
        file_b.write_text(
            "async def b(db):\n    for y in stuff:\n        r = await db.execute(q)\n"
        )

        findings: list[Finding] = []
        _scan_n_plus_one([file_a, file_b], findings)

        assert len(findings) == 2
        assert findings[0].id != findings[1].id
        assert "ALPHA" in findings[0].id
        assert "BETA" in findings[1].id

    def test_id_includes_line_number(self, tmp_path):
        """N+1 finding IDs include file stem and line number."""
        from agents.architect.architect import _scan_n_plus_one

        f = tmp_path / "myservice.py"
        f.write_text(
            "async def run(db):\n"
            "    for item in batch:\n"
            "        await db.execute(query)\n"
        )

        findings: list[Finding] = []
        _scan_n_plus_one([f], findings)

        assert len(findings) == 1
        assert findings[0].id.startswith("ARCH-N+1-MYSERVICE-L")


class TestResolvedRegistryIdMismatchPrevention:
    """Verify that the filter catches findings with mismatched IDs."""

    def test_treb_live_funnel_not_matched_by_treb_001(self):
        """treb-live-funnel-001 must NOT be matched by treb-001 registry entry."""
        fake_registry = {
            "treb-001": {
                "resolution_type": "deferred",
                "resolved_at": "2026-03-12T00:00:00+00:00",
                "reason": "Test",
                "skip_until": "2026-04-15",
            }
        }
        findings = [
            Finding(
                id="treb-live-funnel-001",
                severity="high",
                category="nh_funnel",
                title="NH signup->upload rate critically low",
                detail="d",
            )
        ]
        with _fake_registry(fake_registry):
            result = filter_resolved_findings(findings)

        # treb-001 should NOT suppress treb-live-funnel-001 (different findings)
        assert len(result) == 1, "treb-001 incorrectly suppressed treb-live-funnel-001"

    def test_exact_id_match_suppresses_correctly(self):
        """treb-live-funnel-001 IS suppressed when its exact ID is in registry."""
        fake_registry = {
            "treb-live-funnel-001": {
                "resolution_type": "deferred",
                "resolved_at": "2026-03-29T00:00:00+00:00",
                "reason": "Pre-launch expected",
                "skip_until": "2026-05-01",
            }
        }
        findings = [
            Finding(
                id="treb-live-funnel-001",
                severity="high",
                category="nh_funnel",
                title="NH signup->upload rate critically low",
                detail="d",
            )
        ]
        with _fake_registry(fake_registry):
            result = filter_resolved_findings(findings)

        assert len(result) == 0, "Exact match should suppress the finding"
