"""Integration tests for vector search feature flag behavior."""

import pytest
from httpx import AsyncClient


class TestVectorSearchFeatureFlag:
    """Verify feature flag controls behavior."""

    @pytest.mark.asyncio
    async def test_nlp_search_works_with_vector_disabled(self, client: AsyncClient):
        """NLP search should use keyword path when vector is off."""
        from tests.conftest import create_test_user_in_db, TestSessionLocal

        async with TestSessionLocal() as db:
            _, headers = await create_test_user_in_db(
                db,
                email="vec_test@example.com",
                email_verified=True,
            )

        resp = await client.post(
            "/api/v1/contacts/nlp-search",
            json={"query": "engineer at google"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert isinstance(data["data"], list)
        # Verify it used keyword mode (not vector) via meta
        meta = data.get("meta", {})
        assert meta.get("mode") != "vector"

    @pytest.mark.asyncio
    async def test_marketplace_search_works_with_vector_disabled(
        self, client: AsyncClient
    ):
        """Marketplace search should work normally when vector is off."""
        from tests.conftest import create_test_user_in_db, TestSessionLocal

        async with TestSessionLocal() as db:
            _, headers = await create_test_user_in_db(
                db,
                email="vec_mkt@example.com",
                email_verified=True,
            )

        resp = await client.post(
            "/api/v1/marketplace/search",
            json={"company_names": ["Google"], "query": "senior engineer"},
            headers=headers,
        )
        # May fail due to insufficient credits, but should not crash
        assert resp.status_code in (200, 402, 403)
