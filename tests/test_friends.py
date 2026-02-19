"""Tests for friends system — bilateral friendships, blocks, marketplace integration."""

import uuid as uuid_mod

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.models.user import User
from tests.conftest import TestSessionLocal, create_test_user_in_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def user_a_headers(client: AsyncClient) -> dict:
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email="alice@test.com", full_name="Alice Alpha"
        )
    return headers


@pytest_asyncio.fixture
async def user_b_headers(client: AsyncClient) -> dict:
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email="bob@test.com", full_name="Bob Beta"
        )
    return headers


@pytest_asyncio.fixture
async def user_c_headers(client: AsyncClient) -> dict:
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email="carol@test.com", full_name="Carol Charlie"
        )
    return headers


async def _get_user_id(client: AsyncClient, headers: dict) -> str:
    resp = await client.get("/api/v1/auth/me", headers=headers)
    return resp.json()["data"]["id"]


# ---------------------------------------------------------------------------
# Friend request tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_friend_request(
    client: AsyncClient, user_a_headers: dict, user_b_headers: dict
) -> None:
    b_id = await _get_user_id(client, user_b_headers)
    resp = await client.post(
        "/api/v1/friends/request",
        json={"addressee_id": b_id},
        headers=user_a_headers,
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["status"] == "pending"
    assert data["addressee_id"] == b_id
    assert data["addressee_name"] == "Bob Beta"


@pytest.mark.asyncio
async def test_send_friend_request_self(
    client: AsyncClient, user_a_headers: dict
) -> None:
    a_id = await _get_user_id(client, user_a_headers)
    resp = await client.post(
        "/api/v1/friends/request",
        json={"addressee_id": a_id},
        headers=user_a_headers,
    )
    assert resp.status_code == 422
    assert "yourself" in resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_send_friend_request_nonexistent_user(
    client: AsyncClient, user_a_headers: dict
) -> None:
    resp = await client.post(
        "/api/v1/friends/request",
        json={"addressee_id": str(uuid_mod.uuid4())},
        headers=user_a_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_send_duplicate_request(
    client: AsyncClient, user_a_headers: dict, user_b_headers: dict
) -> None:
    b_id = await _get_user_id(client, user_b_headers)
    await client.post(
        "/api/v1/friends/request",
        json={"addressee_id": b_id},
        headers=user_a_headers,
    )
    # Second request should fail
    resp = await client.post(
        "/api/v1/friends/request",
        json={"addressee_id": b_id},
        headers=user_a_headers,
    )
    assert resp.status_code == 422
    assert "already" in resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_reverse_duplicate_request(
    client: AsyncClient, user_a_headers: dict, user_b_headers: dict
) -> None:
    """B can't send request to A if A already sent one to B."""
    b_id = await _get_user_id(client, user_b_headers)
    a_id = await _get_user_id(client, user_a_headers)

    await client.post(
        "/api/v1/friends/request",
        json={"addressee_id": b_id},
        headers=user_a_headers,
    )
    resp = await client.post(
        "/api/v1/friends/request",
        json={"addressee_id": a_id},
        headers=user_b_headers,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Friend request response tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_accept_friend_request(
    client: AsyncClient, user_a_headers: dict, user_b_headers: dict
) -> None:
    b_id = await _get_user_id(client, user_b_headers)
    req = await client.post(
        "/api/v1/friends/request",
        json={"addressee_id": b_id},
        headers=user_a_headers,
    )
    friendship_id = req.json()["data"]["id"]

    resp = await client.patch(
        f"/api/v1/friends/requests/{friendship_id}",
        json={"action": "accept"},
        headers=user_b_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "accepted"
    assert resp.json()["data"]["responded_at"] is not None


@pytest.mark.asyncio
async def test_decline_friend_request(
    client: AsyncClient, user_a_headers: dict, user_b_headers: dict
) -> None:
    b_id = await _get_user_id(client, user_b_headers)
    req = await client.post(
        "/api/v1/friends/request",
        json={"addressee_id": b_id},
        headers=user_a_headers,
    )
    friendship_id = req.json()["data"]["id"]

    resp = await client.patch(
        f"/api/v1/friends/requests/{friendship_id}",
        json={"action": "decline"},
        headers=user_b_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "declined"


@pytest.mark.asyncio
async def test_requester_cannot_respond(
    client: AsyncClient, user_a_headers: dict, user_b_headers: dict
) -> None:
    """Only the addressee can accept/decline."""
    b_id = await _get_user_id(client, user_b_headers)
    req = await client.post(
        "/api/v1/friends/request",
        json={"addressee_id": b_id},
        headers=user_a_headers,
    )
    friendship_id = req.json()["data"]["id"]

    # A (requester) tries to accept their own request
    resp = await client.patch(
        f"/api/v1/friends/requests/{friendship_id}",
        json={"action": "accept"},
        headers=user_a_headers,
    )
    assert resp.status_code == 404
    assert "error" in resp.json()


@pytest.mark.asyncio
async def test_invalid_action(
    client: AsyncClient, user_a_headers: dict, user_b_headers: dict
) -> None:
    b_id = await _get_user_id(client, user_b_headers)
    req = await client.post(
        "/api/v1/friends/request",
        json={"addressee_id": b_id},
        headers=user_a_headers,
    )
    friendship_id = req.json()["data"]["id"]

    resp = await client.patch(
        f"/api/v1/friends/requests/{friendship_id}",
        json={"action": "ignore"},
        headers=user_b_headers,
    )
    assert resp.status_code == 422  # Pydantic validation


# ---------------------------------------------------------------------------
# Incoming/outgoing request listing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_incoming_requests(
    client: AsyncClient, user_a_headers: dict, user_b_headers: dict
) -> None:
    b_id = await _get_user_id(client, user_b_headers)
    await client.post(
        "/api/v1/friends/request",
        json={"addressee_id": b_id},
        headers=user_a_headers,
    )

    resp = await client.get("/api/v1/friends/requests/incoming", headers=user_b_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["requester_name"] == "Alice Alpha"


@pytest.mark.asyncio
async def test_outgoing_requests(
    client: AsyncClient, user_a_headers: dict, user_b_headers: dict
) -> None:
    b_id = await _get_user_id(client, user_b_headers)
    await client.post(
        "/api/v1/friends/request",
        json={"addressee_id": b_id},
        headers=user_a_headers,
    )

    resp = await client.get("/api/v1/friends/requests/outgoing", headers=user_a_headers)
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 1


# ---------------------------------------------------------------------------
# Friends list and removal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_friends(
    client: AsyncClient, user_a_headers: dict, user_b_headers: dict
) -> None:
    b_id = await _get_user_id(client, user_b_headers)
    req = await client.post(
        "/api/v1/friends/request",
        json={"addressee_id": b_id},
        headers=user_a_headers,
    )
    fid = req.json()["data"]["id"]
    await client.patch(
        f"/api/v1/friends/requests/{fid}",
        json={"action": "accept"},
        headers=user_b_headers,
    )

    # Both users should see each other as friends
    resp_a = await client.get("/api/v1/friends", headers=user_a_headers)
    assert resp_a.status_code == 200
    assert len(resp_a.json()["data"]) == 1
    assert resp_a.json()["data"][0]["full_name"] == "Bob Beta"

    resp_b = await client.get("/api/v1/friends", headers=user_b_headers)
    assert len(resp_b.json()["data"]) == 1
    assert resp_b.json()["data"][0]["full_name"] == "Alice Alpha"


@pytest.mark.asyncio
async def test_search_friends(
    client: AsyncClient, user_a_headers: dict, user_b_headers: dict
) -> None:
    b_id = await _get_user_id(client, user_b_headers)
    req = await client.post(
        "/api/v1/friends/request",
        json={"addressee_id": b_id},
        headers=user_a_headers,
    )
    fid = req.json()["data"]["id"]
    await client.patch(
        f"/api/v1/friends/requests/{fid}",
        json={"action": "accept"},
        headers=user_b_headers,
    )

    resp = await client.get("/api/v1/friends?search=Bob", headers=user_a_headers)
    assert len(resp.json()["data"]) == 1

    resp = await client.get("/api/v1/friends?search=Charlie", headers=user_a_headers)
    assert len(resp.json()["data"]) == 0


@pytest.mark.asyncio
async def test_remove_friend(
    client: AsyncClient, user_a_headers: dict, user_b_headers: dict
) -> None:
    b_id = await _get_user_id(client, user_b_headers)
    req = await client.post(
        "/api/v1/friends/request",
        json={"addressee_id": b_id},
        headers=user_a_headers,
    )
    fid = req.json()["data"]["id"]
    await client.patch(
        f"/api/v1/friends/requests/{fid}",
        json={"action": "accept"},
        headers=user_b_headers,
    )

    # Remove the friendship
    resp = await client.delete(f"/api/v1/friends/{fid}", headers=user_a_headers)
    assert resp.status_code == 204

    # Both users should now have 0 friends
    resp_a = await client.get("/api/v1/friends", headers=user_a_headers)
    assert len(resp_a.json()["data"]) == 0

    resp_b = await client.get("/api/v1/friends", headers=user_b_headers)
    assert len(resp_b.json()["data"]) == 0


@pytest.mark.asyncio
async def test_remove_nonexistent_friend(
    client: AsyncClient, user_a_headers: dict
) -> None:
    resp = await client.delete(
        f"/api/v1/friends/{uuid_mod.uuid4()}", headers=user_a_headers
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Block / unblock tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_block_user(
    client: AsyncClient, user_a_headers: dict, user_b_headers: dict
) -> None:
    b_id = await _get_user_id(client, user_b_headers)
    resp = await client.post(
        "/api/v1/friends/block",
        json={"user_id": b_id},
        headers=user_a_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["blocked_id"] == b_id


@pytest.mark.asyncio
async def test_block_self(client: AsyncClient, user_a_headers: dict) -> None:
    a_id = await _get_user_id(client, user_a_headers)
    resp = await client.post(
        "/api/v1/friends/block",
        json={"user_id": a_id},
        headers=user_a_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_block_auto_unfriends(
    client: AsyncClient, user_a_headers: dict, user_b_headers: dict
) -> None:
    """Blocking someone who is a friend should auto-remove the friendship."""
    b_id = await _get_user_id(client, user_b_headers)

    # Become friends
    req = await client.post(
        "/api/v1/friends/request",
        json={"addressee_id": b_id},
        headers=user_a_headers,
    )
    fid = req.json()["data"]["id"]
    await client.patch(
        f"/api/v1/friends/requests/{fid}",
        json={"action": "accept"},
        headers=user_b_headers,
    )

    # Now block
    await client.post(
        "/api/v1/friends/block",
        json={"user_id": b_id},
        headers=user_a_headers,
    )

    # Friends list should be empty
    resp = await client.get("/api/v1/friends", headers=user_a_headers)
    assert len(resp.json()["data"]) == 0


@pytest.mark.asyncio
async def test_blocked_user_cant_send_request(
    client: AsyncClient, user_a_headers: dict, user_b_headers: dict
) -> None:
    """If A blocks B, B cannot send a friend request to A."""
    a_id = await _get_user_id(client, user_a_headers)
    b_id = await _get_user_id(client, user_b_headers)

    # A blocks B
    await client.post(
        "/api/v1/friends/block",
        json={"user_id": b_id},
        headers=user_a_headers,
    )

    # B tries to send friend request to A
    resp = await client.post(
        "/api/v1/friends/request",
        json={"addressee_id": a_id},
        headers=user_b_headers,
    )
    assert resp.status_code == 403
    assert "error" in resp.json()


@pytest.mark.asyncio
async def test_unblock_user(
    client: AsyncClient, user_a_headers: dict, user_b_headers: dict
) -> None:
    b_id = await _get_user_id(client, user_b_headers)
    await client.post(
        "/api/v1/friends/block",
        json={"user_id": b_id},
        headers=user_a_headers,
    )

    resp = await client.delete(
        f"/api/v1/friends/block/{b_id}",
        headers=user_a_headers,
    )
    assert resp.status_code == 204

    # Now B can send a request
    a_id = await _get_user_id(client, user_a_headers)
    resp = await client.post(
        "/api/v1/friends/request",
        json={"addressee_id": a_id},
        headers=user_b_headers,
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_list_blocked_users(
    client: AsyncClient, user_a_headers: dict, user_b_headers: dict
) -> None:
    b_id = await _get_user_id(client, user_b_headers)
    await client.post(
        "/api/v1/friends/block",
        json={"user_id": b_id},
        headers=user_a_headers,
    )

    resp = await client.get("/api/v1/friends/blocked", headers=user_a_headers)
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 1
    assert resp.json()["data"][0]["full_name"] == "Bob Beta"


@pytest.mark.asyncio
async def test_double_block(
    client: AsyncClient, user_a_headers: dict, user_b_headers: dict
) -> None:
    b_id = await _get_user_id(client, user_b_headers)
    await client.post(
        "/api/v1/friends/block",
        json={"user_id": b_id},
        headers=user_a_headers,
    )
    resp = await client.post(
        "/api/v1/friends/block",
        json={"user_id": b_id},
        headers=user_a_headers,
    )
    assert resp.status_code == 422
    assert "already blocked" in resp.json()["error"]["message"]


# ---------------------------------------------------------------------------
# Service-level tests (friendship_service)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_friend_ids_service() -> None:
    """Service-level test for get_friend_ids used by marketplace."""
    from app.services.friendship_service import (
        get_friend_ids,
        send_friend_request,
        respond_to_request,
    )

    async with TestSessionLocal() as db:
        # Create two users
        u1 = User(email="svc1@test.com", full_name="Svc One", password_hash="x")
        u2 = User(email="svc2@test.com", full_name="Svc Two", password_hash="x")
        db.add_all([u1, u2])
        await db.flush()

        # No friends yet
        ids = await get_friend_ids(u1.id, db)
        assert len(ids) == 0

        # Send and accept request
        f = await send_friend_request(u1.id, u2.id, db)
        await respond_to_request(f.id, u2.id, "accept", db)

        # Now they're friends
        ids = await get_friend_ids(u1.id, db)
        assert u2.id in ids

        ids2 = await get_friend_ids(u2.id, db)
        assert u1.id in ids2
        await db.commit()


@pytest.mark.asyncio
async def test_get_friend_and_fof_ids() -> None:
    """Test friend-of-friend ID computation."""
    from app.services.friendship_service import (
        get_friend_and_fof_ids,
        respond_to_request,
        send_friend_request,
    )

    async with TestSessionLocal() as db:
        u1 = User(email="fof1@test.com", full_name="FoF One", password_hash="x")
        u2 = User(email="fof2@test.com", full_name="FoF Two", password_hash="x")
        u3 = User(email="fof3@test.com", full_name="FoF Three", password_hash="x")
        db.add_all([u1, u2, u3])
        await db.flush()

        # u1 <-> u2 friends
        f1 = await send_friend_request(u1.id, u2.id, db)
        await respond_to_request(f1.id, u2.id, "accept", db)

        # u2 <-> u3 friends
        f2 = await send_friend_request(u2.id, u3.id, db)
        await respond_to_request(f2.id, u3.id, "accept", db)

        # u1's friends = {u2}, FoF = {u3}
        friends, fof = await get_friend_and_fof_ids(u1.id, db)
        assert u2.id in friends
        assert u3.id in fof
        assert u1.id not in fof

        # u3's friends = {u2}, FoF = {u1}
        friends3, fof3 = await get_friend_and_fof_ids(u3.id, db)
        assert u2.id in friends3
        assert u1.id in fof3
        await db.commit()


@pytest.mark.asyncio
async def test_delete_user_friendships() -> None:
    """GDPR deletion hard-removes all friendships and blocks."""
    from app.services.friendship_service import (
        block_user,
        delete_user_friendships,
        respond_to_request,
        send_friend_request,
    )

    async with TestSessionLocal() as db:
        u1 = User(email="del1@test.com", full_name="Del One", password_hash="x")
        u2 = User(email="del2@test.com", full_name="Del Two", password_hash="x")
        u3 = User(email="del3@test.com", full_name="Del Three", password_hash="x")
        db.add_all([u1, u2, u3])
        await db.flush()

        f = await send_friend_request(u1.id, u2.id, db)
        await respond_to_request(f.id, u2.id, "accept", db)
        await block_user(u1.id, u3.id, db)

        counts = await delete_user_friendships(u1.id, db)
        assert counts["friendships"] == 1
        assert counts["blocks"] == 1
        await db.commit()


# ---------------------------------------------------------------------------
# Unauthenticated access
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthenticated_access(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/friends")
    assert resp.status_code == 401

    resp = await client.post(
        "/api/v1/friends/request", json={"addressee_id": str(uuid_mod.uuid4())}
    )
    assert resp.status_code == 401

    resp = await client.get("/api/v1/friends/blocked")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Marketplace friend filter (schema validation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_marketplace_friend_filter_invalid(
    client: AsyncClient, user_a_headers: dict
) -> None:
    """Verify invalid friend_filter values are rejected by Pydantic."""
    # Verify email first (marketplace search requires it)
    async with TestSessionLocal() as db:
        from sqlalchemy import update
        from app.models.user import User

        await db.execute(
            update(User)
            .where(User.email == "alice@test.com")
            .values(email_verified=True)
        )
        await db.commit()

    resp = await client.post(
        "/api/v1/marketplace/search",
        json={
            "company_names": ["Stripe"],
            "friend_filter": "invalid_value",
        },
        headers=user_a_headers,
    )
    assert resp.status_code == 422
    assert "detail" in resp.json()
