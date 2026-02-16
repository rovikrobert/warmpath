"""Job board fetcher — pulls openings from Greenhouse and Lever public APIs.

Both APIs are free and require no authentication. We normalize their
different response formats into a standard dict structure that maps
directly to the job_openings table.
"""

import json
import logging
import re
from datetime import datetime, timezone

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_REMOTE_PATTERNS = re.compile(
    r"\b(remote|anywhere|distributed|work from home|wfh)\b", re.IGNORECASE
)

HTTPX_TIMEOUT = 10.0


class JobFetcher:
    """Fetches and normalizes job listings from ATS platforms."""

    async def fetch_greenhouse_jobs(self, board_name: str) -> list[dict]:
        """Fetch jobs from Greenhouse boards API.

        Endpoint: https://boards-api.greenhouse.io/v1/boards/{board_name}/jobs
        """
        url = f"https://boards-api.greenhouse.io/v1/boards/{board_name}/jobs"
        try:
            async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Greenhouse fetch failed for '%s': %s", board_name, exc)
            return []

        data = resp.json()
        jobs = data.get("jobs", [])

        results: list[dict] = []
        for job in jobs:
            location_name = ""
            loc = job.get("location")
            if isinstance(loc, dict):
                location_name = loc.get("name", "")
            elif isinstance(loc, str):
                location_name = loc

            department = ""
            depts = job.get("departments", [])
            if depts and isinstance(depts[0], dict):
                department = depts[0].get("name", "")

            posted_at = None
            updated = job.get("updated_at")
            if updated:
                try:
                    posted_at = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            results.append(
                {
                    "title": job.get("title", ""),
                    "department": department or None,
                    "location": location_name or None,
                    "url": job.get("absolute_url", ""),
                    "source": "greenhouse",
                    "source_job_id": str(job.get("id", "")),
                    "posted_at": posted_at,
                    "is_remote": bool(_REMOTE_PATTERNS.search(location_name)),
                    "raw_data": job,
                }
            )

        logger.info(
            "Greenhouse: fetched %d jobs for board '%s'", len(results), board_name
        )
        return results

    async def fetch_lever_jobs(self, company_slug: str) -> list[dict]:
        """Fetch jobs from Lever postings API.

        Endpoint: https://api.lever.co/v0/postings/{company_slug}
        """
        url = f"https://api.lever.co/v0/postings/{company_slug}"
        try:
            async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Lever fetch failed for '%s': %s", company_slug, exc)
            return []

        postings = resp.json()
        if not isinstance(postings, list):
            logger.warning("Lever returned non-list for '%s'", company_slug)
            return []

        results: list[dict] = []
        for posting in postings:
            categories = posting.get("categories", {})
            location_name = categories.get("location", "") or ""
            department = categories.get("team", "") or ""

            posted_at = None
            created = posting.get("createdAt")
            if created:
                try:
                    # Lever returns epoch milliseconds
                    posted_at = datetime.fromtimestamp(created / 1000, tz=timezone.utc)
                except (ValueError, TypeError, OSError):
                    pass

            results.append(
                {
                    "title": posting.get("text", ""),
                    "department": department or None,
                    "location": location_name or None,
                    "url": posting.get("hostedUrl", ""),
                    "source": "lever",
                    "source_job_id": posting.get("id", ""),
                    "posted_at": posted_at,
                    "is_remote": bool(_REMOTE_PATTERNS.search(location_name)),
                    "raw_data": posting,
                }
            )

        logger.info("Lever: fetched %d jobs for slug '%s'", len(results), company_slug)
        return results

    async def fetch_jobs_for_company(
        self, company_name: str, board_ids: dict[str, str] | None = None
    ) -> list[dict]:
        """Fetch jobs for a company using the best available source.

        Fallback chain: Greenhouse/Lever boards → career page scraper → empty.
        board_ids is a dict like {"greenhouse": "stripe", "lever": "notion"}.
        """
        from app.services.career_page_fetcher import (
            fetch_career_page,
            lookup_career_page,
        )

        all_jobs: list[dict] = []

        # 1. Try ATS boards (Greenhouse / Lever)
        if board_ids:
            if "greenhouse" in board_ids:
                jobs = await self.fetch_greenhouse_jobs(board_ids["greenhouse"])
                all_jobs.extend(jobs)

            if "lever" in board_ids:
                jobs = await self.fetch_lever_jobs(board_ids["lever"])
                all_jobs.extend(jobs)

        # 2. If ATS boards returned nothing, try career page scraper
        if not all_jobs:
            career_url = lookup_career_page(company_name)
            if career_url:
                logger.info(
                    "No ATS results for '%s', falling back to career page: %s",
                    company_name,
                    career_url,
                )
                all_jobs = await fetch_career_page(career_url)

        logger.info(
            "Fetched %d total jobs for company '%s'", len(all_jobs), company_name
        )
        return all_jobs

    async def match_jobs_to_role(
        self,
        jobs: list[dict],
        target_role: str,
        target_seniority: str | None = None,
    ) -> list[dict]:
        """Score job titles for relevance to a target role.

        Uses Claude API when AI_MOCK_MODE=false, keyword matching otherwise.
        Returns jobs with relevance >= 50, sorted by score descending.
        """
        if not jobs or not target_role:
            return []

        if settings.AI_MOCK_MODE:
            return self._mock_match_jobs(jobs, target_role, target_seniority)

        return await self._ai_match_jobs(jobs, target_role, target_seniority)

    def _mock_match_jobs(
        self,
        jobs: list[dict],
        target_role: str,
        target_seniority: str | None = None,
    ) -> list[dict]:
        """Mock role matching using keyword overlap."""
        role_words = set(target_role.lower().split())
        seniority_words = (
            set(target_seniority.lower().split()) if target_seniority else set()
        )

        scored: list[dict] = []
        for job in jobs:
            title = job.get("title", "").lower()
            title_words = set(title.split())

            # Score based on word overlap
            role_overlap = len(role_words & title_words)
            seniority_overlap = (
                len(seniority_words & title_words) if seniority_words else 0
            )

            if role_overlap == 0:
                # Check for substring match (e.g. "engineer" in "software engineer")
                if any(w in title for w in role_words):
                    role_overlap = 0.5

            if role_overlap == 0:
                continue

            score = min(
                100,
                int(
                    (role_overlap / max(len(role_words), 1)) * 70
                    + seniority_overlap * 30
                ),
            )
            if score >= 50:
                scored.append({**job, "role_relevance": score})

        scored.sort(key=lambda x: x["role_relevance"], reverse=True)
        return scored

    async def _ai_match_jobs(
        self,
        jobs: list[dict],
        target_role: str,
        target_seniority: str | None = None,
    ) -> list[dict]:
        """Use Claude to score job titles for relevance."""
        import anthropic

        titles = [
            {
                "index": i,
                "title": j.get("title", ""),
                "department": j.get("department", ""),
            }
            for i, j in enumerate(jobs)
        ]

        seniority_text = f" at '{target_seniority}' level" if target_seniority else ""
        prompt = f"""Given a user looking for '{target_role}' roles{seniority_text}, score these job titles for relevance 0-100.

JOB TITLES:
{json.dumps(titles, indent=2)}

Return a JSON array of objects with "index" (integer) and "score" (integer 0-100).
Only include jobs scoring >= 50. Return ONLY the JSON array."""

        try:
            client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
            message = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1]
                raw = raw.rsplit("```", 1)[0].strip()

            parsed = json.loads(raw)
            scored: list[dict] = []
            for item in parsed:
                idx = item.get("index")
                score = item.get("score", 0)
                if idx is not None and 0 <= idx < len(jobs) and score >= 50:
                    scored.append({**jobs[idx], "role_relevance": score})

            scored.sort(key=lambda x: x["role_relevance"], reverse=True)
            return scored

        except Exception as exc:
            logger.error("AI role matching failed: %s — falling back to mock", exc)
            return self._mock_match_jobs(jobs, target_role, target_seniority)
