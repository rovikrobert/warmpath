"""Friendship service — bilateral friend requests and unilateral blocks.

Business rules:
- Friend requests require bilateral consent (requester sends, addressee accepts)
- Declined requests are silent — requester sees "pending" until 30-day auto-expire
- Blocks auto-unfriend + cancel pending requests between the pair
- Max 20 pending outbound requests per user (rate limit)
- Account deletion hard-deletes all friendships/blocks (no audit requirement)
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.friendship import UserBlock, UserFriendship
from app.models.user import ConnectorProfile, User
from app.services.audit_logger import log_event
from app.utils.exceptions import (
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)


async def send_friend_request(
    requester_id: uuid.UUID, addressee_id: uuid.UUID, db: AsyncSession
) -> UserFriendship:
    """Send a friend request. Returns the new friendship row."""
    if requester_id == addressee_id:
        raise ValidationError("Cannot send friend request to yourself")

    # Check addressee exists and is active
    addressee = await db.execute(
        select(User).where(User.id == addressee_id, User.deleted_at.is_(None))
    )
    if addressee.scalar_one_or_none() is None:
        raise NotFoundError("User not found")

    # Check not blocked (either direction)
    if await is_blocked(requester_id, addressee_id, db):
        raise ForbiddenError("Cannot send friend request to this user")

    # Check no existing pending/accepted friendship (either direction)
    existing = await db.execute(
        select(UserFriendship).where(
            or_(
                (UserFriendship.requester_id == requester_id)
                & (UserFriendship.addressee_id == addressee_id),
                (UserFriendship.requester_id == addressee_id)
                & (UserFriendship.addressee_id == requester_id),
            ),
            UserFriendship.status.in_(["pending", "accepted"]),
            UserFriendship.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ValidationError(
            "Friend request already exists or you are already friends"
        )

    # Rate limit: max 20 pending outbound requests
    pending_count_result = await db.execute(
        select(func.count()).where(
            UserFriendship.requester_id == requester_id,
            UserFriendship.status == "pending",
            UserFriendship.deleted_at.is_(None),
        )
    )
    if pending_count_result.scalar() >= 20:
        raise RateLimitError("Maximum 20 pending friend requests allowed")

    friendship = UserFriendship(
        requester_id=requester_id,
        addressee_id=addressee_id,
        status="pending",
    )
    db.add(friendship)
    await db.flush()

    await log_event(
        db,
        "friend_request_sent",
        user_id=requester_id,
        metadata={
            "addressee_id": str(addressee_id),
            "friendship_id": str(friendship.id),
        },
    )
    return friendship


async def respond_to_request(
    friendship_id: uuid.UUID, addressee_id: uuid.UUID, action: str, db: AsyncSession
) -> UserFriendship:
    """Accept or decline a friend request. Only the addressee can respond."""
    result = await db.execute(
        select(UserFriendship).where(
            UserFriendship.id == friendship_id,
            UserFriendship.addressee_id == addressee_id,
            UserFriendship.status == "pending",
            UserFriendship.deleted_at.is_(None),
        )
    )
    friendship = result.scalar_one_or_none()
    if friendship is None:
        raise NotFoundError("Friend request not found")

    now = datetime.now(timezone.utc)
    friendship.responded_at = now

    if action == "accept":
        friendship.status = "accepted"
        await log_event(
            db,
            "friend_request_accepted",
            user_id=addressee_id,
            metadata={"friendship_id": str(friendship_id)},
        )
    else:  # decline
        friendship.status = "declined"
        await log_event(
            db,
            "friend_request_declined",
            user_id=addressee_id,
            metadata={"friendship_id": str(friendship_id)},
        )

    await db.flush()
    return friendship


async def get_incoming_requests(
    user_id: uuid.UUID, db: AsyncSession
) -> list[UserFriendship]:
    """Get pending friend requests sent to this user."""
    result = await db.execute(
        select(UserFriendship)
        .where(
            UserFriendship.addressee_id == user_id,
            UserFriendship.status == "pending",
            UserFriendship.deleted_at.is_(None),
        )
        .order_by(UserFriendship.requested_at.desc())
    )
    return list(result.scalars())


async def get_outgoing_requests(
    user_id: uuid.UUID, db: AsyncSession
) -> list[UserFriendship]:
    """Get pending friend requests sent by this user."""
    result = await db.execute(
        select(UserFriendship)
        .where(
            UserFriendship.requester_id == user_id,
            UserFriendship.status == "pending",
            UserFriendship.deleted_at.is_(None),
        )
        .order_by(UserFriendship.requested_at.desc())
    )
    return list(result.scalars())


async def get_friends(
    user_id: uuid.UUID,
    db: AsyncSession,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Get accepted friends with profile info. Returns (friends_list, total_count)."""
    # Find all accepted friendships for this user
    base_where = [
        or_(
            UserFriendship.requester_id == user_id,
            UserFriendship.addressee_id == user_id,
        ),
        UserFriendship.status == "accepted",
        UserFriendship.deleted_at.is_(None),
    ]

    count_result = await db.execute(select(func.count()).where(*base_where))
    total = count_result.scalar()

    friendships_result = await db.execute(
        select(UserFriendship)
        .where(*base_where)
        .order_by(UserFriendship.responded_at.desc())
        .limit(limit)
        .offset(offset)
    )
    friendships = list(friendships_result.scalars())

    if not friendships:
        return [], total

    # Collect friend user IDs (the *other* person in each friendship)
    friend_user_ids = []
    friendship_map: dict[uuid.UUID, UserFriendship] = {}
    for f in friendships:
        friend_id = f.addressee_id if f.requester_id == user_id else f.requester_id
        friend_user_ids.append(friend_id)
        friendship_map[friend_id] = f

    # Load user profiles
    user_query = select(User).where(
        User.id.in_(friend_user_ids), User.deleted_at.is_(None)
    )
    if search:
        user_query = user_query.where(User.full_name.ilike(f"%{search}%"))

    users_result = await db.execute(user_query)
    users = {u.id: u for u in users_result.scalars()}

    # Load connector profiles for headline/company
    profiles: dict[uuid.UUID, ConnectorProfile] = {}
    if friend_user_ids:
        profile_result = await db.execute(
            select(ConnectorProfile).where(
                ConnectorProfile.user_id.in_(friend_user_ids)
            )
        )
        profiles = {p.user_id: p for p in profile_result.scalars()}

    friends_list = []
    for fid in friend_user_ids:
        user = users.get(fid)
        if user is None:
            continue
        profile = profiles.get(fid)
        f = friendship_map[fid]
        friends_list.append(
            {
                "friend_id": fid,
                "full_name": user.full_name,
                "headline": profile.headline if profile else None,
                "current_company": profile.current_company if profile else None,
                "current_title": profile.current_title if profile else None,
                "friend_since": f.responded_at or f.created_at,
            }
        )

    return friends_list, total


async def get_friend_ids(user_id: uuid.UUID, db: AsyncSession) -> set[uuid.UUID]:
    """Return set of user IDs who are accepted friends. Used by marketplace."""
    result = await db.execute(
        select(UserFriendship).where(
            or_(
                UserFriendship.requester_id == user_id,
                UserFriendship.addressee_id == user_id,
            ),
            UserFriendship.status == "accepted",
            UserFriendship.deleted_at.is_(None),
        )
    )
    ids: set[uuid.UUID] = set()
    for f in result.scalars():
        ids.add(f.addressee_id if f.requester_id == user_id else f.requester_id)
    return ids


async def get_friend_and_fof_ids(
    user_id: uuid.UUID, db: AsyncSession
) -> tuple[set[uuid.UUID], set[uuid.UUID]]:
    """Return (friend_ids, friend_of_friend_ids) for extended filtering."""
    friend_ids = await get_friend_ids(user_id, db)
    if not friend_ids:
        return set(), set()

    # Batch-load all friends-of-friends in a single query (avoids N+1)
    fof_result = await db.execute(
        select(UserFriendship).where(
            or_(
                UserFriendship.requester_id.in_(friend_ids),
                UserFriendship.addressee_id.in_(friend_ids),
            ),
            UserFriendship.status == "accepted",
            UserFriendship.deleted_at.is_(None),
        )
    )
    fof_ids: set[uuid.UUID] = set()
    for f in fof_result.scalars():
        fof_ids.add(f.requester_id)
        fof_ids.add(f.addressee_id)

    # Remove self and direct friends from FoF set
    fof_ids.discard(user_id)
    fof_ids -= friend_ids

    return friend_ids, fof_ids


async def remove_friend(
    friendship_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession
) -> None:
    """Soft-delete a friendship. Either party can remove."""
    result = await db.execute(
        select(UserFriendship).where(
            UserFriendship.id == friendship_id,
            or_(
                UserFriendship.requester_id == user_id,
                UserFriendship.addressee_id == user_id,
            ),
            UserFriendship.status == "accepted",
            UserFriendship.deleted_at.is_(None),
        )
    )
    friendship = result.scalar_one_or_none()
    if friendship is None:
        raise NotFoundError("Friendship not found")

    friendship.deleted_at = datetime.now(timezone.utc)
    await log_event(
        db,
        "friend_removed",
        user_id=user_id,
        metadata={"friendship_id": str(friendship_id)},
    )
    await db.flush()


async def block_user(
    blocker_id: uuid.UUID, blocked_id: uuid.UUID, db: AsyncSession
) -> UserBlock:
    """Block a user. Auto-unfriends and cancels pending requests."""
    if blocker_id == blocked_id:
        raise ValidationError("Cannot block yourself")

    # Check target exists
    target = await db.execute(
        select(User).where(User.id == blocked_id, User.deleted_at.is_(None))
    )
    if target.scalar_one_or_none() is None:
        raise NotFoundError("User not found")

    # Check not already blocked
    existing = await db.execute(
        select(UserBlock).where(
            UserBlock.blocker_id == blocker_id,
            UserBlock.blocked_id == blocked_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ValidationError("User is already blocked")

    block = UserBlock(blocker_id=blocker_id, blocked_id=blocked_id)
    db.add(block)

    # Auto-unfriend: soft-delete any active friendship between the pair
    friendships_result = await db.execute(
        select(UserFriendship).where(
            or_(
                (UserFriendship.requester_id == blocker_id)
                & (UserFriendship.addressee_id == blocked_id),
                (UserFriendship.requester_id == blocked_id)
                & (UserFriendship.addressee_id == blocker_id),
            ),
            UserFriendship.deleted_at.is_(None),
            UserFriendship.status.in_(["pending", "accepted"]),
        )
    )
    now = datetime.now(timezone.utc)
    for f in friendships_result.scalars():
        f.deleted_at = now
        f.status = "declined" if f.status == "pending" else f.status

    await db.flush()
    return block


async def unblock_user(
    blocker_id: uuid.UUID, blocked_id: uuid.UUID, db: AsyncSession
) -> None:
    """Remove a block."""
    result = await db.execute(
        delete(UserBlock).where(
            UserBlock.blocker_id == blocker_id,
            UserBlock.blocked_id == blocked_id,
        )
    )
    if result.rowcount == 0:
        raise NotFoundError("Block not found")


async def get_blocked_users(user_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    """Get list of users blocked by this user."""
    result = await db.execute(
        select(UserBlock, User)
        .join(User, UserBlock.blocked_id == User.id)
        .where(UserBlock.blocker_id == user_id)
        .order_by(UserBlock.created_at.desc())
    )
    return [
        {
            "blocked_id": block.blocked_id,
            "full_name": user.full_name,
            "created_at": block.created_at,
        }
        for block, user in result
    ]


async def is_blocked(user_a: uuid.UUID, user_b: uuid.UUID, db: AsyncSession) -> bool:
    """Check if either user has blocked the other."""
    result = await db.execute(
        select(func.count()).where(
            or_(
                (UserBlock.blocker_id == user_a) & (UserBlock.blocked_id == user_b),
                (UserBlock.blocker_id == user_b) & (UserBlock.blocked_id == user_a),
            )
        )
    )
    return result.scalar() > 0


async def delete_user_friendships(
    user_id: uuid.UUID, db: AsyncSession
) -> dict[str, int]:
    """Hard-delete all friendships and blocks for a user (GDPR Article 17)."""
    r1 = await db.execute(
        delete(UserFriendship).where(
            or_(
                UserFriendship.requester_id == user_id,
                UserFriendship.addressee_id == user_id,
            )
        )
    )
    r2 = await db.execute(
        delete(UserBlock).where(
            or_(
                UserBlock.blocker_id == user_id,
                UserBlock.blocked_id == user_id,
            )
        )
    )
    return {"friendships": r1.rowcount, "blocks": r2.rowcount}
