"""Tests for MCP tool Pydantic v2 input models."""

import pytest
from pydantic import ValidationError

from mcp_server.tools.models import (
    GetSchemaInput,
    IndexSessionInput,
    PrivacyAuditLogInput,
    QueryAuditLogInput,
    QuerySqlInput,
    QueryTemplateInput,
    ReadReportInput,
    SaveMemoryInput,
    SearchMemoryInput,
    StripeChargesInput,
    StripeSubscriptionsInput,
    VALID_TEAMS,
)


# ── QueryTemplateInput ───────────────────────────────────────────────


class TestQueryTemplateInput:
    def test_valid_minimal(self):
        m = QueryTemplateInput(name="user_count")
        assert m.name == "user_count"
        assert m.params is None

    def test_valid_with_params(self):
        m = QueryTemplateInput(name="users_by_date", params={"start": "2026-01-01"})
        assert m.params == {"start": "2026-01-01"}

    def test_name_stripped(self):
        m = QueryTemplateInput(name="  spaced  ")
        assert m.name == "spaced"

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            QueryTemplateInput(name="")

    def test_name_too_long(self):
        with pytest.raises(ValidationError):
            QueryTemplateInput(name="x" * 129)

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            QueryTemplateInput(name="ok", bogus=True)


# ── QuerySqlInput ────────────────────────────────────────────────────


class TestQuerySqlInput:
    def test_valid_minimal(self):
        m = QuerySqlInput(sql="SELECT 1")
        assert m.context == "mcp_query"
        assert m.params is None

    def test_valid_full(self):
        m = QuerySqlInput(
            sql="SELECT * FROM users WHERE id = :id",
            params={"id": "abc"},
            context="test_ctx",
        )
        assert m.sql == "SELECT * FROM users WHERE id = :id"
        assert m.context == "test_ctx"

    def test_empty_sql_rejected(self):
        with pytest.raises(ValidationError):
            QuerySqlInput(sql="")

    def test_sql_too_long(self):
        with pytest.raises(ValidationError):
            QuerySqlInput(sql="X" * 10_001)

    def test_context_min_length(self):
        with pytest.raises(ValidationError):
            QuerySqlInput(sql="SELECT 1", context="")

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            QuerySqlInput(sql="SELECT 1", nope=1)


# ── GetSchemaInput ───────────────────────────────────────────────────


class TestGetSchemaInput:
    def test_defaults(self):
        m = GetSchemaInput()
        assert m.table_name is None

    def test_with_table(self):
        m = GetSchemaInput(table_name="contacts")
        assert m.table_name == "contacts"

    def test_empty_table_name_rejected(self):
        with pytest.raises(ValidationError):
            GetSchemaInput(table_name="")

    def test_table_name_too_long(self):
        with pytest.raises(ValidationError):
            GetSchemaInput(table_name="t" * 129)


# ── SearchMemoryInput ────────────────────────────────────────────────


class TestSearchMemoryInput:
    def test_valid_minimal(self):
        m = SearchMemoryInput(query="find bugs")
        assert m.top_k == 10
        assert m.team is None

    def test_valid_full(self):
        m = SearchMemoryInput(
            query="deployment",
            team="ops_team",
            top_k=50,
            bm25_weight=0.3,
            temporal_half_life=30,
        )
        assert m.top_k == 50
        assert m.bm25_weight == 0.3

    def test_empty_query_rejected(self):
        with pytest.raises(ValidationError):
            SearchMemoryInput(query="")

    def test_query_too_long(self):
        with pytest.raises(ValidationError):
            SearchMemoryInput(query="x" * 2001)

    def test_top_k_bounds(self):
        with pytest.raises(ValidationError):
            SearchMemoryInput(query="q", top_k=0)
        with pytest.raises(ValidationError):
            SearchMemoryInput(query="q", top_k=101)

    def test_bm25_weight_bounds(self):
        with pytest.raises(ValidationError):
            SearchMemoryInput(query="q", bm25_weight=-0.1)
        with pytest.raises(ValidationError):
            SearchMemoryInput(query="q", bm25_weight=1.1)

    def test_temporal_half_life_bounds(self):
        with pytest.raises(ValidationError):
            SearchMemoryInput(query="q", temporal_half_life=0)
        with pytest.raises(ValidationError):
            SearchMemoryInput(query="q", temporal_half_life=366)


# ── SaveMemoryInput ──────────────────────────────────────────────────


class TestSaveMemoryInput:
    def test_valid_minimal(self):
        m = SaveMemoryInput(content="a bug was found")
        assert m.importance == 0.5
        assert m.ttl_hours is None

    def test_importance_clamped_high(self):
        m = SaveMemoryInput(content="note", importance=5.0)
        assert m.importance == 1.0

    def test_importance_clamped_low(self):
        m = SaveMemoryInput(content="note", importance=-1.0)
        assert m.importance == 0.0

    def test_empty_content_rejected(self):
        with pytest.raises(ValidationError):
            SaveMemoryInput(content="")

    def test_content_too_long(self):
        with pytest.raises(ValidationError):
            SaveMemoryInput(content="x" * 50_001)

    def test_ttl_hours_bounds(self):
        with pytest.raises(ValidationError):
            SaveMemoryInput(content="c", ttl_hours=0)
        with pytest.raises(ValidationError):
            SaveMemoryInput(content="c", ttl_hours=8761)

    def test_summary_max_length(self):
        with pytest.raises(ValidationError):
            SaveMemoryInput(content="c", summary="s" * 501)

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            SaveMemoryInput(content="c", unknown_field="x")


# ── IndexSessionInput ───────────────────────────────────────────────


class TestIndexSessionInput:
    def test_valid_minimal(self):
        m = IndexSessionInput(session_summary="did stuff")
        assert m.key_learnings is None

    def test_valid_with_learnings(self):
        m = IndexSessionInput(
            session_summary="fixed bugs",
            key_learnings=["bug A fixed", "bug B fixed"],
        )
        assert len(m.key_learnings) == 2

    def test_empty_summary_rejected(self):
        with pytest.raises(ValidationError):
            IndexSessionInput(session_summary="")

    def test_summary_too_long(self):
        with pytest.raises(ValidationError):
            IndexSessionInput(session_summary="x" * 50_001)


# ── QueryAuditLogInput ──────────────────────────────────────────────


class TestQueryAuditLogInput:
    def test_defaults(self):
        m = QueryAuditLogInput()
        assert m.action is None
        assert m.limit == 50

    def test_limit_clamped_low(self):
        m = QueryAuditLogInput(limit=-5)
        assert m.limit == 1

    def test_limit_clamped_high(self):
        m = QueryAuditLogInput(limit=9999)
        assert m.limit == 1000

    def test_action_max_length(self):
        with pytest.raises(ValidationError):
            QueryAuditLogInput(action="a" * 129)


# ── PrivacyAuditLogInput ────────────────────────────────────────────


class TestPrivacyAuditLogInput:
    def test_defaults(self):
        m = PrivacyAuditLogInput()
        assert m.limit == 100

    def test_limit_clamped_low(self):
        m = PrivacyAuditLogInput(limit=-10)
        assert m.limit == 1

    def test_limit_clamped_high(self):
        m = PrivacyAuditLogInput(limit=999)
        assert m.limit == 500


# ── ReadReportInput ──────────────────────────────────────────────────


class TestReadReportInput:
    def test_valid(self):
        m = ReadReportInput(team="agents", filename="scan-2026-03-01.json")
        assert m.team == "agents"

    def test_all_valid_teams(self):
        for team in VALID_TEAMS:
            m = ReadReportInput(team=team, filename="report.json")
            assert m.team == team

    def test_invalid_team(self):
        with pytest.raises(ValidationError, match="Unknown team"):
            ReadReportInput(team="hackers", filename="report.json")

    def test_path_traversal_dotdot(self):
        with pytest.raises(ValidationError, match="path traversal"):
            ReadReportInput(team="agents", filename="../etc/passwd")

    def test_path_traversal_slash(self):
        with pytest.raises(ValidationError, match="path traversal"):
            ReadReportInput(team="agents", filename="sub/file.json")

    def test_path_traversal_backslash(self):
        with pytest.raises(ValidationError, match="path traversal"):
            ReadReportInput(team="agents", filename="sub\\file.json")

    def test_empty_filename_rejected(self):
        with pytest.raises(ValidationError):
            ReadReportInput(team="agents", filename="")

    def test_filename_too_long(self):
        with pytest.raises(ValidationError):
            ReadReportInput(team="agents", filename="f" * 256)


# ── StripeSubscriptionsInput ─────────────────────────────────────────


class TestStripeSubscriptionsInput:
    def test_defaults(self):
        m = StripeSubscriptionsInput()
        assert m.status == "active"

    def test_custom_status(self):
        m = StripeSubscriptionsInput(status="canceled")
        assert m.status == "canceled"

    def test_status_max_length(self):
        with pytest.raises(ValidationError):
            StripeSubscriptionsInput(status="x" * 33)


# ── StripeChargesInput ───────────────────────────────────────────────


class TestStripeChargesInput:
    def test_defaults(self):
        m = StripeChargesInput()
        assert m.limit == 25
        assert m.created_after is None

    def test_limit_bounds(self):
        with pytest.raises(ValidationError):
            StripeChargesInput(limit=0)
        with pytest.raises(ValidationError):
            StripeChargesInput(limit=101)

    def test_created_after_negative(self):
        with pytest.raises(ValidationError):
            StripeChargesInput(created_after=-1)

    def test_valid_created_after(self):
        m = StripeChargesInput(created_after=1700000000)
        assert m.created_after == 1700000000
