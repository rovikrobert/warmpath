"""Friends API — bilateral friendships and unilateral blocks.

Endpoints:
  POST   /friends/request                  — send friend request
  GET    /friends/requests/incoming         — pending requests to me
  GET    /friends/requests/outgoing         — pending requests from me
  PATCH  /friends/requests/{friendship_id}  — accept or decline
  GET    /friends                           — my accepted friends
  DELETE /friends/{friendship_id}           — remove a friend
  POST   /friends/block                     — block a user
  DELETE /friends/block/{user_id}           — unblock a user
  GET    /friends/blocked                   — my blocked users
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import ConnectorProfile, User
from app.schemas.friendship import (
    BlockedUserResponse,
    BlockUserRequest,
    FriendRequestAction,
    FriendRequestCreate,
    FriendRequestResponse,
    FriendSummary,
)
from app.services.friendship_service import (
    block_user,
    get_blocked_users,
    get_friends,
    get_incoming_requests,
    get_outgoing_requests,
    remove_friend,
    respond_to_request,
    send_friend_request,
    unblock_user,
)
from app.utils.security import get_current_user

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _enrich_request(
    friendship: "UserFriendship", db: AsyncSession
) -> dict:
    """Add requester/addressee profile info to a friendship response."""
    from sqlalchemy import select

    data = FriendRequestResponse.model_validate(friendship).model_dump(mode="json")

    # Load requester info
    req_result = await db.execute(select(User).where(User.id == friendship.requester_id))
    requester = req_result.scalar_one_or_none()
    if requester:
        data["requester_name"] = requester.full_name

    addr_result = await db.execute(select(User).where(User.id == friendship.addressee_id))
    addressee = addr_result.scalar_one_or_none()
    if addressee:
        data["addressee_name"] = addressee.full_name

    # Load connector profiles for headline/company
    profile_result = await db.execute(
        select(ConnectorProfile).where(
            ConnectorProfile.user_id.in_([friendship.requester_id, friendship.addressee_id])
        )
    )
    for p in profile_result.scalars():
        if p.user_id == friendship.requester_id:
            data["requester_headline"] = p.headline
            data["requester_company"] = p.current_company
        else:
            data["addressee_headline"] = p.headline

    return data


# ---------------------------------------------------------------------------
# POST /friends/request
# ---------------------------------------------------------------------------


@router.post("/request", status_code=201)
async def create_friend_request(
    body: FriendRequestCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Send a friend request to another user."""
    friendship = await send_friend_request(current_user.id, body.addressee_id, db)
    data = await _enrich_request(friendship, db)
    return {"data": data, "meta": {}}


# ---------------------------------------------------------------------------
# GET /friends/requests/incoming
# ---------------------------------------------------------------------------


@router.get("/requests/incoming")
async def incoming_requests(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get pending friend requests sent to me."""
    friendships = await get_incoming_requests(current_user.id, db)
    data = []
    for f in friendships:
        data.append(await _enrich_request(f, db))
    return {"data": data, "meta": {"total": len(data)}}


# ---------------------------------------------------------------------------
# GET /friends/requests/outgoing
# ---------------------------------------------------------------------------


@router.get("/requests/outgoing")
async def outgoing_requests(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get pending friend requests I sent."""
    friendships = await get_outgoing_requests(current_user.id, db)
    data = []
    for f in friendships:
        data.append(await _enrich_request(f, db))
    return {"data": data, "meta": {"total": len(data)}}


# ---------------------------------------------------------------------------
# PATCH /friends/requests/{friendship_id}
# ---------------------------------------------------------------------------


@router.patch("/requests/{friendship_id}")
async def action_friend_request(
    friendship_id: uuid.UUID,
    body: FriendRequestAction,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Accept or decline a friend request. Only the addressee can respond."""
    friendship = await respond_to_request(
        friendship_id, current_user.id, body.action, db
    )
    data = FriendRequestResponse.model_validate(friendship).model_dump(mode="json")
    return {"data": data, "meta": {}}


# ---------------------------------------------------------------------------
# GET /friends
# ---------------------------------------------------------------------------


@router.get("")
async def list_friends(
    search: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List my accepted friends with profile info."""
    friends, total = await get_friends(
        current_user.id, db, search=search, limit=limit, offset=offset
    )
    return {"data": friends, "meta": {"total": total}}


# ---------------------------------------------------------------------------
# DELETE /friends/{friendship_id}
# ---------------------------------------------------------------------------


@router.delete("/{friendship_id}", status_code=204)
async def delete_friend(
    friendship_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a friend (soft-delete). Either party can remove."""
    await remove_friend(friendship_id, current_user.id, db)


# ---------------------------------------------------------------------------
# POST /friends/block
# ---------------------------------------------------------------------------


@router.post("/block", status_code=201)
async def block_user_endpoint(
    body: BlockUserRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Block a user. Auto-unfriends and cancels pending requests."""
    block = await block_user(current_user.id, body.user_id, db)
    return {
        "data": {"blocker_id": str(block.blocker_id), "blocked_id": str(block.blocked_id)},
        "meta": {},
    }


# ---------------------------------------------------------------------------
# DELETE /friends/block/{user_id}
# ---------------------------------------------------------------------------


@router.delete("/block/{user_id}", status_code=204)
async def unblock_user_endpoint(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Unblock a user."""
    await unblock_user(current_user.id, user_id, db)


# ---------------------------------------------------------------------------
# GET /friends/blocked
# ---------------------------------------------------------------------------


@router.get("/blocked")
async def list_blocked(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List users I have blocked."""
    blocked = await get_blocked_users(current_user.id, db)
    return {"data": blocked, "meta": {"total": len(blocked)}}
