"""Keyset (cursor-based) pagination utilities.

Keyset pagination avoids the performance cliff of OFFSET on large tables.
Instead of ``OFFSET 5000``, it uses ``WHERE created_at < :cursor`` which
leverages indexes efficiently regardless of page depth.

Usage::

    from app.utils.pagination import KeysetPage, apply_keyset_pagination

    page = apply_keyset_pagination(
        query, cursor=request_cursor, limit=50,
        order_col=Contact.created_at, id_col=Contact.id, direction="desc",
    )
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class KeysetPage(BaseModel):
    """Response metadata for keyset-paginated endpoints."""

    next_cursor: str | None = None
    has_more: bool = False
    count: int = 0


def encode_cursor(values: dict[str, Any]) -> str:
    """Encode pagination state as a URL-safe cursor string."""
    serializable = {}
    for k, v in values.items():
        if isinstance(v, datetime):
            serializable[k] = v.isoformat()
        elif isinstance(v, UUID):
            serializable[k] = str(v)
        else:
            serializable[k] = v
    return base64.urlsafe_b64encode(json.dumps(serializable).encode()).decode()


def decode_cursor(cursor: str) -> dict[str, Any]:
    """Decode a cursor string back to pagination state."""
    try:
        return json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except Exception:
        return {}


def apply_keyset_pagination(
    query,
    cursor: str | None,
    limit: int,
    order_col,
    id_col,
    direction: str = "desc",
):
    """Apply keyset pagination to a SQLAlchemy query.

    Args:
        query: Base SQLAlchemy select statement
        cursor: Encoded cursor from previous page (None for first page)
        limit: Max items per page
        order_col: The column to order by (e.g., Contact.created_at)
        id_col: The tie-breaking ID column (e.g., Contact.id)
        direction: "asc" or "desc"

    Returns:
        Modified query with WHERE + ORDER BY + LIMIT applied
    """
    if cursor:
        decoded = decode_cursor(cursor)
        val = decoded.get("v")
        tie = decoded.get("id")
        if val is not None and tie is not None:
            if direction == "desc":
                query = query.where(
                    (order_col < val) | ((order_col == val) & (id_col < tie))
                )
            else:
                query = query.where(
                    (order_col > val) | ((order_col == val) & (id_col > tie))
                )

    if direction == "desc":
        query = query.order_by(order_col.desc(), id_col.desc())
    else:
        query = query.order_by(order_col.asc(), id_col.asc())

    # Fetch limit + 1 to detect has_more
    query = query.limit(limit + 1)
    return query
