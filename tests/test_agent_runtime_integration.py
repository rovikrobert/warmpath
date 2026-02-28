"""Integration test -- full event -> graph -> findings pipeline.

Mocks the actual scanner execution but tests the full LangGraph flow
end-to-end: event ingestion -> classify -> cos_route -> team_dispatch ->
synthesize -> evaluate -> terminal state.
"""

import pytest
from unittest.mock import patch

from app.agent_runtime.events.ingestion import create_event
from app.agent_runtime.runner import process_event
from app.agent_runtime.teams.base import TeamRunner
from app.agent_runtime.teams.engineering import EngineeringTeam
from app.agent_runtime.teams.gtm import GtmTeam
from app.agent_runtime.teams.ops import OpsTeam


@pytest.fixture(autouse=True)
def _reset_compiled_graph():
    """Reset the cached compiled graph before each test.

    The runner module caches the compiled graph in a module-level global.
    We must clear it so each test gets a fresh graph with the current
    mock targets properly wired.
    """
    import app.agent_runtime.runner as runner_mod

    runner_mod._compiled_graph = None
    yield
    runner_mod._compiled_graph = None


async def _passthrough_augment(self, findings, event, trust_level, budget_status):
    """Skip SDK augmentation in integration tests — return findings unchanged."""
    return findings


@pytest.mark.asyncio
async def test_incident_event_flows_through_full_graph():
    """Incident event -> classify (critical) -> route -> dispatch -> synthesize -> end."""
    event = create_event(
        event_type="incident",
        source="railway",
        payload={"error_count": 20, "sample_errors": ["500 Internal"]},
    )

    eng_findings = [
        {
            "id": "f1",
            "severity": "high",
            "category": "infrastructure",
            "title": "Error spike detected",
            "source_team": "engineering",
        }
    ]

    with (
        patch.object(TeamRunner, "augment_with_sdk", _passthrough_augment),
        patch.object(EngineeringTeam, "run_scanners", return_value=eng_findings),
        patch.object(OpsTeam, "run_scanners", return_value=[]),
    ):
        result = await process_event(event)

        assert result["priority"] == "critical"
        assert "engineering" in result["routed_teams"]
        assert len(result["findings"]) >= 1
        assert result["findings"][0]["title"] == "Error spike detected"
        assert result["findings"][0]["source_team"] == "engineering"
        assert result["handoffs"] == []


@pytest.mark.asyncio
async def test_code_change_event_flows_through_graph():
    """Code change event is classified as medium and routed to engineering."""
    event = create_event(
        event_type="code_change",
        source="github",
        payload={"branch": "fix/auth", "commits": ["abc"]},
    )

    with (
        patch.object(TeamRunner, "augment_with_sdk", _passthrough_augment),
        patch.object(EngineeringTeam, "run_scanners", return_value=[]),
    ):
        result = await process_event(event)

        assert result["priority"] == "medium"
        assert "engineering" in result["routed_teams"]
        assert result["findings"] == []
        assert result["handoffs"] == []


@pytest.mark.asyncio
async def test_security_code_change_gets_high_priority():
    """Code change touching auth files is classified as high priority."""
    event = create_event(
        event_type="code_change",
        source="github",
        payload={
            "branch": "fix/auth-bypass",
            "commits": ["def456"],
            "files_changed": ["app/middleware/auth.py", "app/api/v1/auth.py"],
        },
    )

    sec_findings = [
        {
            "id": "f-sec",
            "severity": "high",
            "category": "security",
            "title": "Auth middleware modified",
            "source_team": "engineering",
        }
    ]

    with (
        patch.object(TeamRunner, "augment_with_sdk", _passthrough_augment),
        patch.object(EngineeringTeam, "run_scanners", return_value=sec_findings),
    ):
        result = await process_event(event)

        assert result["priority"] == "high"
        assert "engineering" in result["routed_teams"]
        assert len(result["findings"]) == 1
        assert result["findings"][0]["category"] == "security"


@pytest.mark.asyncio
async def test_multiple_findings_accumulated_in_dispatch():
    """Multiple scanner findings are all collected in the final state."""
    event = create_event(
        event_type="incident",
        source="railway",
        payload={"error_count": 15, "sample_errors": ["timeout", "502"]},
    )

    eng_findings = [
        {
            "id": "f1",
            "severity": "high",
            "category": "infrastructure",
            "title": "Connection pool exhausted",
            "source_team": "engineering",
        },
        {
            "id": "f2",
            "severity": "medium",
            "category": "performance",
            "title": "Response time degradation",
            "source_team": "engineering",
        },
    ]

    # Critical incidents route to ["engineering", "ops"] — mock both
    with (
        patch.object(TeamRunner, "augment_with_sdk", _passthrough_augment),
        patch.object(EngineeringTeam, "run_scanners", return_value=eng_findings),
        patch.object(OpsTeam, "run_scanners", return_value=[]),
    ):
        result = await process_event(event)

        assert result["priority"] == "critical"
        assert len(result["findings"]) == 2
        titles = {f["title"] for f in result["findings"]}
        assert "Connection pool exhausted" in titles
        assert "Response time degradation" in titles


@pytest.mark.asyncio
async def test_event_with_no_matching_teams_still_completes():
    """External signal events route to gtm (no engineering scanners)."""
    event = create_event(
        event_type="external_signal",
        source="competitor_tracker",
        payload={"signal_type": "competitor_update", "competitor": "Teamable"},
    )

    with (
        patch.object(TeamRunner, "augment_with_sdk", _passthrough_augment),
        patch.object(GtmTeam, "run_scanners", return_value=[]),
    ):
        result = await process_event(event)

        assert result["priority"] == "low"
        assert "gtm" in result["routed_teams"]
        assert result["findings"] == []
        assert result["handoffs"] == []


# --- SDK augmentation integration tests ---


@pytest.mark.asyncio
async def test_sdk_augmentation_upgrades_finding_severity():
    """Full pipeline: scan findings are augmented by SDK session analysis."""
    from unittest.mock import AsyncMock

    event = create_event(
        event_type="code_change",
        source="github",
        payload={"branch": "fix/db-leak", "commits": ["aaa"]},
    )

    scanner_findings = [
        {
            "id": "f1",
            "severity": "medium",
            "category": "infrastructure",
            "title": "Connection leak detected",
            "source_team": "engineering",
        }
    ]

    sdk_output = {
        "messages": [
            {
                "role": "assistant",
                "content": (
                    "## Finding: Connection leak detected\n"
                    "**Validated:** yes\n"
                    "**Adjusted Severity:** critical\n"
                    "**Root Cause:** Missing connection.close() in error path\n"
                    "**Proposed Fix:** Add finally block in db_session()\n"
                    "**Cross-Team Impact:** ops — affects uptime SLA\n"
                ),
            }
        ],
        "model": "claude-sonnet-4-20250514",
        "cost_usd": 0.02,
        "num_turns": 1,
    }

    with (
        patch.object(EngineeringTeam, "run_scanners", return_value=scanner_findings),
        patch(
            "app.agent_runtime.teams.base.run_sdk_session",
            AsyncMock(return_value=sdk_output),
        ),
    ):
        result = await process_event(event)

    assert len(result["findings"]) >= 1
    upgraded = [
        f for f in result["findings"] if f["title"] == "Connection leak detected"
    ]
    assert len(upgraded) == 1
    assert upgraded[0]["severity"] == "critical"
    assert upgraded[0]["sdk_augmented"] is True
    assert "Missing connection.close()" in upgraded[0].get("root_cause", "")


@pytest.mark.asyncio
async def test_sdk_augmentation_skipped_when_budget_exceeded():
    """Budget exceeded → SDK skipped, raw scanner findings returned."""
    from unittest.mock import AsyncMock

    from app.agent_runtime.cost_guard import BudgetStatus

    event = create_event(
        event_type="code_change",
        source="github",
        payload={"branch": "fix/minor", "commits": ["bbb"]},
    )

    scanner_findings = [
        {
            "id": "f1",
            "severity": "low",
            "category": "code_quality",
            "title": "Unused import",
            "source_team": "engineering",
        }
    ]

    mock_sdk = AsyncMock()
    with (
        patch.object(EngineeringTeam, "run_scanners", return_value=scanner_findings),
        patch(
            "app.agent_runtime.teams.base.run_sdk_session",
            mock_sdk,
        ),
        patch(
            "app.agent_runtime.runner._get_budget_status",
            AsyncMock(return_value=BudgetStatus.OK),
        ),
    ):
        result = await process_event(event)

    assert len(result["findings"]) == 1
    assert result["findings"][0]["title"] == "Unused import"


@pytest.mark.asyncio
async def test_sdk_augmentation_skipped_when_trust_observer():
    """Trust level OBSERVER → SDK skipped, raw scanner findings returned."""
    from unittest.mock import AsyncMock

    from app.agent_runtime.trust import TrustLevel

    event = create_event(
        event_type="code_change",
        source="github",
        payload={"branch": "chore/docs", "commits": ["ccc"]},
    )

    scanner_findings = [
        {
            "id": "f1",
            "severity": "low",
            "category": "docs",
            "title": "README outdated",
            "source_team": "engineering",
        }
    ]

    mock_sdk = AsyncMock()
    # Override _get_compiled_graph to inject trust_level=OBSERVER in config
    import app.agent_runtime.runner as runner_mod
    from app.agent_runtime.graph import build_graph

    graph = build_graph().compile()
    runner_mod._compiled_graph = graph

    with (
        patch.object(EngineeringTeam, "run_scanners", return_value=scanner_findings),
        patch("app.agent_runtime.teams.base.run_sdk_session", mock_sdk),
    ):
        # Invoke graph directly with trust_level=OBSERVER in config
        result = await graph.ainvoke(
            {
                "event": event,
                "routed_teams": ["engineering"],
                "priority": "low",
                "findings": [],
                "actions": [],
                "needs_human": False,
                "human_decision": "",
                "handoffs": [],
            },
            config={
                "configurable": {
                    "trust_level": TrustLevel.OBSERVER,
                    "budget_status": "ok",
                },
                "recursion_limit": 30,
            },
        )

    # SDK should NOT have been called because trust < RECOMMENDER
    mock_sdk.assert_not_called()
    assert len(result["findings"]) == 1
    assert result["findings"][0]["title"] == "README outdated"


@pytest.mark.asyncio
async def test_multi_team_dispatch_each_team_gets_sdk_session():
    """Multiple routed teams each run their own SDK augmentation session."""
    event = create_event(
        event_type="incident",
        source="railway",
        payload={"error_count": 25, "sample_errors": ["OOM"]},
    )

    eng_findings = [
        {
            "id": "e1",
            "severity": "high",
            "category": "infrastructure",
            "title": "OOM kill spike",
            "source_team": "engineering",
        }
    ]
    ops_findings = [
        {
            "id": "o1",
            "severity": "medium",
            "category": "operations",
            "title": "Scaling policy not triggered",
            "source_team": "ops",
        }
    ]

    sdk_call_teams = []

    async def _tracking_augment(self, findings, event, trust_level, budget_status):
        """Track which teams get SDK augmentation calls."""
        sdk_call_teams.append(self.team_name)
        return findings  # passthrough

    with (
        patch.object(TeamRunner, "augment_with_sdk", _tracking_augment),
        patch.object(EngineeringTeam, "run_scanners", return_value=eng_findings),
        patch.object(OpsTeam, "run_scanners", return_value=ops_findings),
    ):
        result = await process_event(event)

    # Both teams should have had augmentation called
    assert "engineering" in sdk_call_teams
    assert "ops" in sdk_call_teams
    assert len(result["findings"]) == 2
    titles = {f["title"] for f in result["findings"]}
    assert "OOM kill spike" in titles
    assert "Scaling policy not triggered" in titles
