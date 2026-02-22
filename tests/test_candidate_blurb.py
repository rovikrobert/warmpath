"""Tests for candidate blurb generation service."""

import pytest
from unittest.mock import MagicMock
from app.services.candidate_blurb import generate_candidate_blurb


@pytest.fixture
def mock_profile():
    profile = MagicMock()
    profile.headline = "Senior Backend Engineer | Distributed Systems"
    profile.current_title = "Senior Backend Engineer"
    profile.current_company = "Datadog"
    profile.bio_summary = "5 years building payments infrastructure"
    profile.industry = "Technology"
    profile.location = "San Francisco"
    profile.github_url = "https://github.com/janedoe"
    profile.portfolio_url = "https://janedoe.dev"
    profile.work_history = [
        {
            "company": "Stripe",
            "title": "Backend Engineer",
            "start_date": "2022",
            "end_date": "2024",
        },
        {
            "company": "Meta",
            "title": "Software Engineer",
            "start_date": "2019",
            "end_date": "2022",
        },
    ]
    return profile


@pytest.fixture
def mock_contact():
    contact = MagicMock()
    contact.full_name = "John Smith"
    contact.current_title = "Senior Engineer"
    contact.current_company = "Stripe"
    contact.location = "San Francisco"
    contact.relationship_type = "former_colleague"
    contact.how_you_know = "Worked together on Payments team"
    return contact


@pytest.fixture
def mock_prefs():
    prefs = MagicMock()
    prefs.target_role = "Staff Engineer"
    prefs.target_seniority = "staff"
    return prefs


class TestMockBlurb:
    """Tests for deterministic mock blurb generation."""

    @pytest.mark.asyncio
    async def test_specific_role_blurb_includes_key_fields(
        self, mock_profile, mock_contact, mock_prefs
    ):
        blurb = await generate_candidate_blurb(
            profile=mock_profile,
            contact=mock_contact,
            prefs=mock_prefs,
            request_type="specific_role",
            job_title="Staff Engineer, Payments",
        )
        assert "Senior Backend Engineer" in blurb or "Datadog" in blurb
        assert "Stripe" in blurb
        assert "Staff Engineer" in blurb
        assert len(blurb) > 50

    @pytest.mark.asyncio
    async def test_general_networking_blurb_softer_framing(
        self, mock_profile, mock_contact, mock_prefs
    ):
        blurb = await generate_candidate_blurb(
            profile=mock_profile,
            contact=mock_contact,
            prefs=mock_prefs,
            request_type="general_networking",
            exploration_context="Learning about eng culture at Stripe",
        )
        assert "Datadog" in blurb or "Senior Backend Engineer" in blurb
        assert len(blurb) > 50

    @pytest.mark.asyncio
    async def test_blurb_includes_github_when_available(
        self, mock_profile, mock_contact, mock_prefs
    ):
        blurb = await generate_candidate_blurb(
            profile=mock_profile,
            contact=mock_contact,
            prefs=mock_prefs,
            request_type="specific_role",
            job_title="Staff Engineer",
        )
        assert "github" in blurb.lower()

    @pytest.mark.asyncio
    async def test_blurb_without_profile_still_works(self, mock_contact, mock_prefs):
        blurb = await generate_candidate_blurb(
            profile=None,
            contact=mock_contact,
            prefs=mock_prefs,
            request_type="specific_role",
            job_title="Staff Engineer",
        )
        assert len(blurb) > 20

    @pytest.mark.asyncio
    async def test_blurb_detects_work_history_overlap(
        self, mock_profile, mock_contact, mock_prefs
    ):
        blurb = await generate_candidate_blurb(
            profile=mock_profile,
            contact=mock_contact,
            prefs=mock_prefs,
            request_type="specific_role",
            job_title="Staff Engineer",
        )
        assert blurb.lower().count("stripe") >= 1
