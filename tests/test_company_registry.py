"""Tests for the DB-backed company board registry.

Covers: model CRUD, service layer, API endpoints, DB-first lookup,
fallback to static dict, seed, and verify.
"""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.models.user import User
from app.services.board_registry import BOARD_REGISTRY, lookup_or_discover_boards
from app.services.registry_service import (
    batch_discover,
    create_board,
    get_board_by_key,
    list_boards,
    lookup_boards_db,
    seed_from_static,
    update_board,
    verify_board,
)
from tests.conftest import TestSessionLocal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict:
    """Create a test user and return auth headers."""
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "registry@test.com",
            "password": "Testpass123",
            "full_name": "Registry Tester",
        },
    )
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "registry@test.com", "password": "Testpass123"},
    )
    token = login_res.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def admin_headers(client: AsyncClient) -> dict:
    """Create an admin user and return auth headers."""
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "regadmin@test.com",
            "password": "Testpass123",
            "full_name": "Registry Admin",
        },
    )
    # Promote to admin directly in DB
    async with TestSessionLocal() as session:
        from sqlalchemy import update

        await session.execute(
            update(User).where(User.email == "regadmin@test.com").values(is_admin=True)
        )
        await session.commit()

    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "regadmin@test.com", "password": "Testpass123"},
    )
    token = login_res.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def db_session():
    """Yield a test DB session."""
    async with TestSessionLocal() as session:
        yield session


# ---------------------------------------------------------------------------
# Service Layer — CRUD
# ---------------------------------------------------------------------------


class TestRegistryServiceCRUD:
    @pytest.mark.asyncio
    async def test_create_board(self, db_session):
        board = await create_board(
            db_session,
            company_key="testcorp",
            display_name="TestCorp",
            board_source="greenhouse",
            board_slug="testcorp",
            region="US / Global",
        )
        await db_session.commit()
        assert board.company_key == "testcorp"
        assert board.board_source == "greenhouse"
        assert board.is_active is True

    @pytest.mark.asyncio
    async def test_create_duplicate_raises(self, db_session):
        await create_board(
            db_session,
            company_key="dupcorp",
            display_name="DupCorp",
            board_source="lever",
            board_slug="dupcorp",
        )
        await db_session.flush()
        with pytest.raises(ValueError, match="already exists"):
            await create_board(
                db_session,
                company_key="dupcorp",
                display_name="DupCorp2",
                board_source="lever",
                board_slug="dupcorp2",
            )

    @pytest.mark.asyncio
    async def test_create_invalid_source_raises(self, db_session):
        with pytest.raises(ValueError, match="board_source must be one of"):
            await create_board(
                db_session,
                company_key="badsource",
                display_name="BadSource",
                board_source="indeed",
                board_slug="bad",
            )

    @pytest.mark.asyncio
    async def test_get_board_by_key(self, db_session):
        await create_board(
            db_session,
            company_key="findme",
            display_name="FindMe",
            board_source="ashby",
            board_slug="findme-inc",
        )
        await db_session.flush()

        found = await get_board_by_key(db_session, "findme")
        assert found is not None
        assert found.board_slug == "findme-inc"

        missing = await get_board_by_key(db_session, "nope")
        assert missing is None

    @pytest.mark.asyncio
    async def test_get_board_by_key_case_insensitive(self, db_session):
        await create_board(
            db_session,
            company_key="casecorp",
            display_name="CaseCorp",
            board_source="greenhouse",
            board_slug="casecorp",
        )
        await db_session.flush()

        found = await get_board_by_key(db_session, "  CaseCorp  ")
        assert found is not None

    @pytest.mark.asyncio
    async def test_update_board(self, db_session):
        board = await create_board(
            db_session,
            company_key="updateme",
            display_name="UpdateMe",
            board_source="greenhouse",
            board_slug="updateme",
        )
        await db_session.flush()

        board = await update_board(
            db_session,
            board,
            display_name="Updated Corp",
            career_page_url="https://example.com/careers",
        )
        assert board.display_name == "Updated Corp"
        assert board.career_page_url == "https://example.com/careers"

    @pytest.mark.asyncio
    async def test_update_invalid_source_raises(self, db_session):
        board = await create_board(
            db_session,
            company_key="badsrcupd",
            display_name="BadSrcUpd",
            board_source="greenhouse",
            board_slug="badsrcupd",
        )
        await db_session.flush()

        with pytest.raises(ValueError, match="board_source must be one of"):
            await update_board(db_session, board, board_source="indeed")

    @pytest.mark.asyncio
    async def test_list_boards(self, db_session):
        for i in range(3):
            await create_board(
                db_session,
                company_key=f"list{i}",
                display_name=f"List{i}",
                board_source="greenhouse",
                board_slug=f"list{i}",
                region="US / Global" if i < 2 else "India",
            )
        await db_session.flush()

        boards, total = await list_boards(db_session)
        assert total == 3
        assert len(boards) == 3

        boards, total = await list_boards(db_session, region="India")
        assert total == 1
        assert boards[0].company_key == "list2"

    @pytest.mark.asyncio
    async def test_list_boards_pagination(self, db_session):
        for i in range(5):
            await create_board(
                db_session,
                company_key=f"page{i}",
                display_name=f"Page{i}",
                board_source="lever",
                board_slug=f"page{i}",
            )
        await db_session.flush()

        boards, total = await list_boards(db_session, page=1, per_page=2)
        assert total == 5
        assert len(boards) == 2

        boards2, _ = await list_boards(db_session, page=2, per_page=2)
        assert len(boards2) == 2
        # Different page
        assert boards[0].company_key != boards2[0].company_key


# ---------------------------------------------------------------------------
# Service Layer — Lookup + Seed
# ---------------------------------------------------------------------------


class TestRegistryServiceLookup:
    @pytest.mark.asyncio
    async def test_lookup_boards_db(self, db_session):
        await create_board(
            db_session,
            company_key="dbcorp",
            display_name="DbCorp",
            board_source="greenhouse",
            board_slug="dbcorp-slug",
        )
        await db_session.flush()

        result = await lookup_boards_db(db_session, "dbcorp")
        assert result == {"greenhouse": "dbcorp-slug"}

    @pytest.mark.asyncio
    async def test_lookup_boards_db_career_page(self, db_session):
        await create_board(
            db_session,
            company_key="careercorp",
            display_name="CareerCorp",
            board_source="career_page",
            career_page_url="https://careercorp.com/jobs",
        )
        await db_session.flush()

        result = await lookup_boards_db(db_session, "careercorp")
        assert result == {"career_page": "https://careercorp.com/jobs"}

    @pytest.mark.asyncio
    async def test_lookup_boards_db_inactive_returns_none(self, db_session):
        board = await create_board(
            db_session,
            company_key="inactivecorp",
            display_name="InactiveCorp",
            board_source="greenhouse",
            board_slug="inactive",
        )
        await db_session.flush()
        await update_board(db_session, board, is_active=False)
        await db_session.flush()

        result = await lookup_boards_db(db_session, "inactivecorp")
        assert result is None

    @pytest.mark.asyncio
    async def test_seed_from_static(self, db_session):
        count = await seed_from_static(db_session)
        await db_session.commit()

        assert count == len(BOARD_REGISTRY)

        # Second seed is idempotent
        count2 = await seed_from_static(db_session)
        assert count2 == 0

        # Verify some entries
        stripe = await get_board_by_key(db_session, "stripe")
        assert stripe is not None
        assert stripe.board_source == "greenhouse"
        assert stripe.board_slug == "stripe"
        assert stripe.region == "US / Global"

        grab = await get_board_by_key(db_session, "grab")
        assert grab is not None
        assert grab.board_source == "career_page"
        assert grab.career_page_url == "https://grab.careers/jobs/"
        assert grab.region == "Singapore / SEA"


class TestRegistryVerify:
    @pytest.mark.asyncio
    async def test_verify_career_page_always_succeeds(self, db_session):
        board = await create_board(
            db_session,
            company_key="verifycpage",
            display_name="VerifyCPage",
            board_source="career_page",
            career_page_url="https://example.com/careers",
        )
        await db_session.flush()

        result = await verify_board(db_session, board)
        assert result is True
        assert board.verified_at is not None

    @pytest.mark.asyncio
    async def test_verify_ats_success(self, db_session):
        board = await create_board(
            db_session,
            company_key="verifyats",
            display_name="VerifyATS",
            board_source="greenhouse",
            board_slug="verifyats",
        )
        await db_session.flush()

        with patch(
            "app.services.board_registry._probe_ats",
            new_callable=AsyncMock,
            return_value={"greenhouse": "verifyats"},
        ):
            result = await verify_board(db_session, board)
        assert result is True
        assert board.is_active is True

    @pytest.mark.asyncio
    async def test_verify_ats_failure_deactivates(self, db_session):
        board = await create_board(
            db_session,
            company_key="verifyfail",
            display_name="VerifyFail",
            board_source="lever",
            board_slug="verifyfail",
        )
        await db_session.flush()

        with patch(
            "app.services.board_registry._probe_ats",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await verify_board(db_session, board)
        assert result is False
        assert board.is_active is False


# ---------------------------------------------------------------------------
# lookup_or_discover_boards — DB-first fallback chain
# ---------------------------------------------------------------------------


class TestBatchDiscover:
    @pytest.mark.asyncio
    async def test_batch_discover_finds_ats(self, db_session):
        """Batch discover should probe ATS and persist results."""
        with patch(
            "app.services.registry_service.discover_boards",
            new_callable=AsyncMock,
            return_value={"greenhouse": "newcorp"},
        ):
            results = await batch_discover(db_session, ["NewCorp"])
            await db_session.commit()

        assert "newcorp" in results
        assert results["newcorp"]["status"] == "discovered"
        assert results["newcorp"]["board_source"] == "greenhouse"

        # Verify persisted to DB
        board = await get_board_by_key(db_session, "newcorp")
        assert board is not None
        assert board.board_source == "greenhouse"
        assert board.is_active is True
        assert board.verified_at is not None

    @pytest.mark.asyncio
    async def test_batch_discover_skips_existing(self, db_session):
        """Batch discover should skip companies already in the DB."""
        await create_board(
            db_session,
            company_key="existcorp",
            display_name="ExistCorp",
            board_source="lever",
            board_slug="existcorp",
        )
        await db_session.flush()

        results = await batch_discover(db_session, ["ExistCorp"])
        assert results["existcorp"]["status"] == "exists"
        assert results["existcorp"]["board_source"] == "lever"

    @pytest.mark.asyncio
    async def test_batch_discover_not_found(self, db_session):
        """Batch discover should mark companies where no ATS is found."""
        with patch(
            "app.services.registry_service.discover_boards",
            new_callable=AsyncMock,
            return_value=None,
        ):
            results = await batch_discover(db_session, ["GhostCorp"])

        assert results["ghostcorp"]["status"] == "not_found"
        assert results["ghostcorp"]["board_source"] is None

    @pytest.mark.asyncio
    async def test_batch_discover_multiple(self, db_session):
        """Batch discover handles multiple companies in one call."""
        await create_board(
            db_session,
            company_key="already",
            display_name="Already",
            board_source="greenhouse",
            board_slug="already",
        )
        await db_session.flush()

        async def mock_discover(name: str):
            key = name.strip().lower()
            if key == "found":
                return {"ashby": "found-inc"}
            return None

        with patch(
            "app.services.registry_service.discover_boards",
            side_effect=mock_discover,
        ):
            results = await batch_discover(db_session, ["Already", "Found", "Missing"])
            await db_session.commit()

        assert results["already"]["status"] == "exists"
        assert results["found"]["status"] == "discovered"
        assert results["missing"]["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_batch_discover_dedupes_within_batch(self, db_session):
        """Duplicate names in the same batch should be processed once."""
        with patch(
            "app.services.registry_service.discover_boards",
            new_callable=AsyncMock,
            return_value={"greenhouse": "dupcorp"},
        ) as mock_fn:
            results = await batch_discover(
                db_session, ["DupCorp", "dupcorp", "  DUPCORP  "]
            )

        # discover_boards called only once despite 3 entries
        assert mock_fn.call_count == 1
        assert len(results) == 1
        assert "dupcorp" in results


class TestLookupOrDiscoverWithDB:
    @pytest.mark.asyncio
    async def test_db_entry_takes_priority(self, db_session):
        """DB entry should be returned before checking static dict."""
        await create_board(
            db_session,
            company_key="stripe",
            display_name="Stripe (DB)",
            board_source="ashby",
            board_slug="stripe-custom",
        )
        await db_session.flush()

        result, was_discovered = await lookup_or_discover_boards("stripe", db_session)
        assert result == {"ashby": "stripe-custom"}
        assert was_discovered is False

    @pytest.mark.asyncio
    async def test_falls_back_to_static_dict(self, db_session):
        """If not in DB, should fall back to static BOARD_REGISTRY."""
        # "coinbase" is in static but not in DB
        result, was_discovered = await lookup_or_discover_boards("coinbase", db_session)
        assert result is not None
        assert "greenhouse" in result
        assert was_discovered is False


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------


class TestRegistryAPI:
    @pytest.mark.asyncio
    async def test_list_empty(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/registry", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"] == []
        assert data["meta"]["total"] == 0

    @pytest.mark.asyncio
    async def test_create_and_get(
        self, client: AsyncClient, admin_headers: dict, auth_headers: dict
    ):
        resp = await client.post(
            "/api/v1/registry",
            headers=admin_headers,
            json={
                "company_key": "apicorp",
                "display_name": "API Corp",
                "board_source": "greenhouse",
                "board_slug": "apicorp",
                "region": "US / Global",
            },
        )
        assert resp.status_code == 201
        board = resp.json()["data"]
        assert board["company_key"] == "apicorp"
        assert board["is_active"] is True

        # GET by key (any user)
        resp2 = await client.get("/api/v1/registry/apicorp", headers=auth_headers)
        assert resp2.status_code == 200
        assert resp2.json()["data"]["display_name"] == "API Corp"

    @pytest.mark.asyncio
    async def test_create_non_admin_forbidden(
        self, client: AsyncClient, auth_headers: dict
    ):
        resp = await client.post(
            "/api/v1/registry",
            headers=auth_headers,
            json={
                "company_key": "noadmin",
                "display_name": "No Admin",
                "board_source": "greenhouse",
                "board_slug": "noadmin",
            },
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_create_duplicate_409(self, client: AsyncClient, admin_headers: dict):
        body = {
            "company_key": "dupapikey",
            "display_name": "DupAPI",
            "board_source": "lever",
            "board_slug": "dupapikey",
        }
        resp1 = await client.post("/api/v1/registry", headers=admin_headers, json=body)
        assert resp1.status_code == 201

        resp2 = await client.post("/api/v1/registry", headers=admin_headers, json=body)
        assert resp2.status_code == 409

    @pytest.mark.asyncio
    async def test_get_not_found(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/registry/nonexistent", headers=auth_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_update(self, client: AsyncClient, admin_headers: dict):
        create_resp = await client.post(
            "/api/v1/registry",
            headers=admin_headers,
            json={
                "company_key": "patchcorp",
                "display_name": "PatchCorp",
                "board_source": "greenhouse",
                "board_slug": "patchcorp",
            },
        )
        board_id = create_resp.json()["data"]["id"]

        resp = await client.patch(
            f"/api/v1/registry/{board_id}",
            headers=admin_headers,
            json={"display_name": "PatchCorp Updated", "is_active": False},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["display_name"] == "PatchCorp Updated"
        assert resp.json()["data"]["is_active"] is False

    @pytest.mark.asyncio
    async def test_patch_non_admin_forbidden(
        self, client: AsyncClient, admin_headers: dict, auth_headers: dict
    ):
        create_resp = await client.post(
            "/api/v1/registry",
            headers=admin_headers,
            json={
                "company_key": "nopatchcorp",
                "display_name": "NoPatchCorp",
                "board_source": "greenhouse",
                "board_slug": "nopatchcorp",
            },
        )
        board_id = create_resp.json()["data"]["id"]

        resp = await client.patch(
            f"/api/v1/registry/{board_id}",
            headers=auth_headers,
            json={"display_name": "Should Fail"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_patch_not_found(self, client: AsyncClient, admin_headers: dict):
        import uuid

        fake_id = str(uuid.uuid4())
        resp = await client.patch(
            f"/api/v1/registry/{fake_id}",
            headers=admin_headers,
            json={"display_name": "Nope"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_verify_endpoint(self, client: AsyncClient, admin_headers: dict):
        create_resp = await client.post(
            "/api/v1/registry",
            headers=admin_headers,
            json={
                "company_key": "verifyme",
                "display_name": "VerifyMe",
                "board_source": "career_page",
                "career_page_url": "https://verifyme.com/jobs",
            },
        )
        board_id = create_resp.json()["data"]["id"]

        # Verify is read-only probe — any user can do it
        resp = await client.post(
            f"/api/v1/registry/{board_id}/verify",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["verified"] is True

    @pytest.mark.asyncio
    async def test_seed_endpoint(self, client: AsyncClient, admin_headers: dict):
        resp = await client.post("/api/v1/registry/seed", headers=admin_headers)
        assert resp.status_code == 200
        seeded = resp.json()["data"]["seeded"]
        assert seeded == len(BOARD_REGISTRY)

        # Second call is idempotent
        resp2 = await client.post("/api/v1/registry/seed", headers=admin_headers)
        assert resp2.json()["data"]["seeded"] == 0

    @pytest.mark.asyncio
    async def test_seed_non_admin_forbidden(
        self, client: AsyncClient, auth_headers: dict
    ):
        resp = await client.post("/api/v1/registry/seed", headers=auth_headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_list_with_region_filter(
        self, client: AsyncClient, admin_headers: dict, auth_headers: dict
    ):
        # Seed first (admin)
        await client.post("/api/v1/registry/seed", headers=admin_headers)

        # List (any user)
        resp = await client.get("/api/v1/registry?region=India", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["meta"]["total"] > 0
        for board in data["data"]:
            assert board["region"] == "India"

    @pytest.mark.asyncio
    async def test_list_with_active_filter(
        self, client: AsyncClient, admin_headers: dict, auth_headers: dict
    ):
        # Create an inactive board (admin)
        create_resp = await client.post(
            "/api/v1/registry",
            headers=admin_headers,
            json={
                "company_key": "deadcorp",
                "display_name": "DeadCorp",
                "board_source": "greenhouse",
                "board_slug": "deadcorp",
            },
        )
        board_id = create_resp.json()["data"]["id"]
        await client.patch(
            f"/api/v1/registry/{board_id}",
            headers=admin_headers,
            json={"is_active": False},
        )

        # List (any user)
        resp = await client.get(
            "/api/v1/registry?is_active=false", headers=auth_headers
        )
        assert resp.status_code == 200
        keys = [b["company_key"] for b in resp.json()["data"]]
        assert "deadcorp" in keys

    @pytest.mark.asyncio
    async def test_discover_endpoint(self, client: AsyncClient, admin_headers: dict):
        with patch(
            "app.services.registry_service.discover_boards",
            new_callable=AsyncMock,
            return_value={"greenhouse": "discoveredcorp"},
        ):
            resp = await client.post(
                "/api/v1/registry/discover",
                headers=admin_headers,
                json={"companies": ["DiscoveredCorp", "DiscoveredCorp"]},
            )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["summary"]["discovered"] == 1
        assert data["summary"]["total"] == 1
        assert data["results"]["discoveredcorp"]["status"] == "discovered"

    @pytest.mark.asyncio
    async def test_discover_non_admin_forbidden(
        self, client: AsyncClient, auth_headers: dict
    ):
        resp = await client.post(
            "/api/v1/registry/discover",
            headers=auth_headers,
            json={"companies": ["SomeCorp"]},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_discover_empty_list_rejected(
        self, client: AsyncClient, admin_headers: dict
    ):
        resp = await client.post(
            "/api/v1/registry/discover",
            headers=admin_headers,
            json={"companies": []},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/registry")
        assert resp.status_code == 401
