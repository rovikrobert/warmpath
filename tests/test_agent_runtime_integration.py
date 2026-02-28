"""Integration test -- full event -> graph -> findings pipeline.

Mocks the actual scanner execution but tests the full LangGraph flow
end-to-end: event ingestion -> classify -> cos_route -> team_dispatch ->
synthesize -> evaluate -> terminal state.
"""

import pytest
from unittest.mock import patch

from app.agent_runtime.events.ingestion import create_event
from app.agent_runtime.runner import process_event


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


@pytest.mark.asyncio
async def test_incident_event_flows_through_full_graph():
    """Incident event -> classify (critical) -> route -> dispatch -> synthesize -> end."""
    event = create_event(
        event_type="incident",
        source="railway",
        payload={"error_count": 20, "sample_errors": ["500 Internal"]},
    )

    with patch(
        "app.agent_runtime.teams.engineering.run_existing_scanners",
        return_value=[
            {
                "id": "f1",
                "severity": "high",
                "category": "infrastructure",
                "title": "Error spike detected",
                "source_team": "engineering",
            }
        ],
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

    with patch(
        "app.agent_runtime.teams.engineering.run_existing_scanners",
        return_value=[],
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

    with patch(
        "app.agent_runtime.teams.engineering.run_existing_scanners",
        return_value=[
            {
                "id": "f-sec",
                "severity": "high",
                "category": "security",
                "title": "Auth middleware modified",
                "source_team": "engineering",
            }
        ],
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

    with patch(
        "app.agent_runtime.teams.engineering.run_existing_scanners",
        return_value=[
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
        ],
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

    # No engineering scanners should run since routed_teams won't include engineering
    result = await process_event(event)

    assert result["priority"] == "low"
    assert "gtm" in result["routed_teams"]
    assert result["findings"] == []
    assert result["handoffs"] == []
