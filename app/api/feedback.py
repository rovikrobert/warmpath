"""Feedback API — collect user thumbs-up/down on features.

Endpoints:
  POST   /feedback  — submit feedback (thumbs up/down + optional comment)

Also syncs beta feedback to the Notion Beta Feedback database (best-effort,
non-blocking). Requires NOTION_API_KEY in environment.
"""

import asyncio
import logging
import uuid
from functools import partial

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.enrichment import UserFeedback
from app.models.user import User
from app.utils.security import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

NOTION_BETA_FEEDBACK_DB = "30b1a870-fe4a-81b4-9b9c-e1abfb30eb3c"


class FeedbackRequest(BaseModel):
    feature: str = Field(..., min_length=1, max_length=100)
    rating: int = Field(..., ge=-1, le=1)  # -1 down, 0 neutral, 1 up
    resource_id: uuid.UUID | None = None
    comment: str | None = Field(None, max_length=1000)


def _sync_feedback_to_notion(
    feature: str,
    rating: int,
    comment: str | None,
    user_email: str,
) -> None:
    """Sync feedback to Notion Beta Feedback database. Best-effort, never raises."""
    try:
        from agents.shared.notion_client import NotionClient

        client = NotionClient()
        if not client.enabled:
            return

        # Map rating to category
        category = {1: "Praise", 0: "Suggestion", -1: "Bug"}.get(rating, "Other")

        # Extract page from feature string (e.g. "beta_feedback:/dashboard" -> "Dashboard")
        page_feature = "Other"
        if ":" in feature:
            path = feature.split(":", 1)[1].strip("/")
            # Capitalize first segment
            first_segment = path.split("/")[0].capitalize() if path else ""
            page_map = {
                "Dashboard": "Dashboard", "Contacts": "Contacts",
                "Search": "Search", "Marketplace": "Marketplace",
                "Coach": "Coach", "Applications": "Applications",
                "Settings": "Settings", "Onboarding": "Onboarding",
                "Signup": "Signup", "Invite": "Other",
            }
            page_feature = page_map.get(first_segment, "Other")

        # Parse user comment from metadata lines
        user_comment = ""
        if comment:
            lines = comment.split("\n")
            # First line(s) before metadata markers are the user comment
            user_lines = [l for l in lines if not l.startswith("[")]
            user_comment = "\n".join(user_lines).strip()

        summary = user_comment[:80] if user_comment else f"{category} on {page_feature}"

        properties = {
            "Name": NotionClient.title_property(summary),
            "Category": NotionClient.select_property(category),
            "Page/Feature": NotionClient.select_property(page_feature),
            "Severity": NotionClient.select_property(
                "Annoying" if rating == -1 else "Just a thought"
            ),
            "Description": NotionClient.rich_text_property(comment or ""),
            "Status": NotionClient.select_property("New"),
            "Feedback Type": NotionClient.select_property(
                "Quick Bug" if rating == -1 else "Detailed Feedback"
            ),
            "Contact Info": NotionClient.rich_text_property(user_email),
        }

        client.create_page(
            database_id=NOTION_BETA_FEEDBACK_DB,
            properties=properties,
        )
        logger.info("Beta feedback synced to Notion for %s", user_email)
    except Exception:
        logger.exception("Failed to sync feedback to Notion (non-critical)")


@router.post("")
async def submit_feedback(
    body: FeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Submit feedback on a feature (search results, intro, coaching, etc.)."""
    fb = UserFeedback(
        user_id=current_user.id,
        feature=body.feature,
        rating=body.rating,
        resource_id=body.resource_id,
        comment=body.comment,
    )
    db.add(fb)
    await db.commit()
    await db.refresh(fb)

    # Sync to Notion (non-blocking, best-effort)
    loop = asyncio.get_event_loop()
    loop.run_in_executor(
        None,
        partial(
            _sync_feedback_to_notion,
            feature=body.feature,
            rating=body.rating,
            comment=body.comment,
            user_email=current_user.email,
        ),
    )

    return {
        "data": {
            "id": str(fb.id),
            "feature": fb.feature,
            "rating": fb.rating,
        },
        "meta": {},
    }
