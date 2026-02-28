"""Tests for vector-enhanced job matching."""

import pytest
from unittest.mock import AsyncMock, patch


class TestVectorJobMatch:
    """Vector search for job-to-role matching."""

    @pytest.mark.asyncio
    async def test_vector_match_returns_scored_jobs(self):
        from app.services.job_fetcher import _vector_match_jobs

        jobs = [
            {"title": "Backend Engineer", "location": "Singapore"},
            {"title": "Data Analyst", "location": "Remote"},
        ]

        # Simulate: query embedding finds Backend Engineer as closer
        mock_results = [
            {
                "id": "point-1",
                "score": 0.92,
                "payload": {
                    "doc_type": "job",
                    "title": "Backend Engineer",
                    "company": "Stripe",
                },
            },
            {
                "id": "point-2",
                "score": 0.45,
                "payload": {
                    "doc_type": "job",
                    "title": "Data Analyst",
                    "company": "Stripe",
                },
            },
        ]

        with (
            patch(
                "app.services.embedding_service.generate_embeddings",
                new_callable=AsyncMock,
                return_value=[[0.1] * 1536],
            ),
            patch(
                "app.services.vector_service.search_similar",
                new_callable=AsyncMock,
                return_value=mock_results,
            ),
        ):
            matched = await _vector_match_jobs(jobs, "backend engineer", "Stripe")

        # Only jobs with score >= 0.5 (mapped to relevance >= 50)
        assert len(matched) == 1
        assert matched[0]["title"] == "Backend Engineer"
        assert matched[0]["role_relevance"] >= 50

    @pytest.mark.asyncio
    async def test_match_jobs_to_role_passes_company_name(self):
        """match_jobs_to_role should pass company_name to _vector_match_jobs."""
        from app.services.job_fetcher import JobFetcher

        fetcher = JobFetcher()
        jobs = [{"title": "Backend Engineer", "department": "Engineering"}]

        with (
            patch(
                "app.services.job_fetcher.settings",
                VECTOR_SEARCH_ENABLED=True,
                AI_MOCK_MODE=True,
            ),
            patch(
                "app.services.job_fetcher._vector_match_jobs",
                new_callable=AsyncMock,
                return_value=[{**jobs[0], "role_relevance": 90}],
            ) as mock_vec,
        ):
            result = await fetcher.match_jobs_to_role(
                jobs, "Backend Engineer", company_name="Stripe"
            )

        mock_vec.assert_called_once_with(jobs, "Backend Engineer", "Stripe")
        assert len(result) == 1
        assert result[0]["role_relevance"] == 90

    @pytest.mark.asyncio
    async def test_match_jobs_to_role_skips_vector_without_company(self):
        """When company_name is empty, should skip vector path."""
        from app.services.job_fetcher import JobFetcher

        fetcher = JobFetcher()
        jobs = [{"title": "Backend Engineer", "department": "Engineering"}]

        with (
            patch(
                "app.services.job_fetcher.settings",
                VECTOR_SEARCH_ENABLED=True,
                AI_MOCK_MODE=True,
            ),
            patch(
                "app.services.job_fetcher._vector_match_jobs",
                new_callable=AsyncMock,
            ) as mock_vec,
        ):
            # No company_name → falls through to mock matcher
            await fetcher.match_jobs_to_role(jobs, "Backend Engineer")

        mock_vec.assert_not_called()

    @pytest.mark.asyncio
    async def test_vector_match_fallback_on_failure(self):
        from app.services.job_fetcher import _vector_match_jobs

        with patch(
            "app.services.embedding_service.generate_embeddings",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await _vector_match_jobs([], "role", "company")

        assert result == []
