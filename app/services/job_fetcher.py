"""Job board fetcher — pulls openings from Greenhouse and Lever public APIs.

Both APIs are free and require no authentication. We normalize their
different response formats into a standard dict structure that maps
directly to the job_openings table.
"""

import contextlib
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

# Some ATS systems prepend numeric IDs to job titles
_LEADING_ID_PATTERN = re.compile(r"^\d{6,}\s+")

HTTPX_TIMEOUT = 3.0


def _clean_job_title(title: str) -> str:
    """Strip leading numeric IDs and normalize whitespace in job titles."""
    title = _LEADING_ID_PATTERN.sub("", title).strip()
    return title


async def _vector_match_jobs(
    jobs: list[dict],
    target_role: str,
    company_name: str,
) -> list[dict]:
    """Match jobs to target role using vector similarity.

    Returns jobs with role_relevance score (0-100), filtered to >= 50.
    """
    if not jobs or not target_role:
        return []

    from app.services.embedding_service import generate_embeddings
    from app.services.vector_service import search_similar

    vectors = await generate_embeddings([target_role])
    if not vectors:
        return []

    results = await search_similar(
        query_vector=vectors[0],
        doc_type="job",
        limit=50,
        filters={"company": company_name},
    )

    # Build lookup: normalized title → vector score
    score_map = {}
    for r in results:
        title = r["payload"].get("title", "").lower().strip()
        score_map[title] = r["score"]

    matched = []
    for job in jobs:
        title = job.get("title", "").lower().strip()
        vector_score = score_map.get(title, 0.0)
        # Map cosine similarity (0-1) to relevance (0-100)
        relevance = int(vector_score * 100)
        if relevance >= 50:
            matched.append({**job, "role_relevance": relevance})

    return sorted(matched, key=lambda j: j["role_relevance"], reverse=True)


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
                with contextlib.suppress(ValueError, TypeError):
                    posted_at = datetime.fromisoformat(updated.replace("Z", "+00:00"))

            results.append(
                {
                    "title": _clean_job_title(job.get("title", "")),
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
                with contextlib.suppress(ValueError, TypeError, OSError):
                    # Lever returns epoch milliseconds
                    posted_at = datetime.fromtimestamp(created / 1000, tz=timezone.utc)

            results.append(
                {
                    "title": _clean_job_title(posting.get("text", "")),
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

    async def fetch_ashby_jobs(self, org_slug: str) -> list[dict]:
        """Fetch jobs from Ashby public posting API.

        Endpoint: https://api.ashbyhq.com/posting-api/job-board/{org_slug}
        """
        url = f"https://api.ashbyhq.com/posting-api/job-board/{org_slug}"
        try:
            async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Ashby fetch failed for '%s': %s", org_slug, exc)
            return []

        data = resp.json()
        jobs = data.get("jobs", [])

        results: list[dict] = []
        for job in jobs:
            if not job.get("isListed", True):
                continue

            location_name = job.get("location", "") or ""
            department = job.get("department", "") or job.get("team", "") or ""
            is_remote = job.get("isRemote") or bool(
                _REMOTE_PATTERNS.search(location_name)
            )

            posted_at = None
            published = job.get("publishedAt")
            if published:
                with contextlib.suppress(ValueError, TypeError):
                    posted_at = datetime.fromisoformat(published.replace("Z", "+00:00"))

            results.append(
                {
                    "title": _clean_job_title(job.get("title", "")),
                    "department": department or None,
                    "location": location_name or None,
                    "url": job.get("jobUrl") or job.get("applyUrl") or "",
                    "source": "ashby",
                    "source_job_id": str(job.get("id", "")),
                    "posted_at": posted_at,
                    "is_remote": bool(is_remote),
                    "raw_data": job,
                }
            )

        logger.info("Ashby: fetched %d jobs for org '%s'", len(results), org_slug)
        return results

    async def fetch_jobs_for_company(
        self,
        company_name: str,
        board_ids: dict[str, str] | None = None,
        location_hint: str | None = None,
    ) -> list[dict]:
        """Fetch jobs for a company using the best available source.

        Fallback chain: Greenhouse/Lever boards → career page scraper → empty.
        board_ids is a dict like {"greenhouse": "stripe", "lever": "notion"}.
        location_hint is an optional location string (e.g. "Singapore") passed
        to JobSpy and Adzuna for region-aware searching.
        """
        from app.services.career_page_fetcher import (
            fetch_career_page,
            lookup_career_page,
        )

        all_jobs: list[dict] = []

        # 1. Try ATS boards (Greenhouse / Lever / Ashby)
        if board_ids:
            if "greenhouse" in board_ids:
                jobs = await self.fetch_greenhouse_jobs(board_ids["greenhouse"])
                all_jobs.extend(jobs)

            if "lever" in board_ids:
                jobs = await self.fetch_lever_jobs(board_ids["lever"])
                all_jobs.extend(jobs)

            if "ashby" in board_ids:
                jobs = await self.fetch_ashby_jobs(board_ids["ashby"])
                all_jobs.extend(jobs)

            if "career_page" in board_ids:
                all_jobs = await fetch_career_page(board_ids["career_page"])

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

        # 3. If still nothing, try JobSpy (Indeed + LinkedIn + optionally other boards)
        if not all_jobs:
            from app.services.jobspy_fetcher import search_jobs_via_jobspy

            logger.info(
                "No ATS/career-page results for '%s', trying JobSpy",
                company_name,
            )
            all_jobs = await search_jobs_via_jobspy(
                company_name, location_hint=location_hint
            )

        # 4. If still nothing and aggregator configured, try Adzuna
        if not all_jobs and settings.ADZUNA_APP_ID:
            from app.services.job_aggregator import search_jobs_by_company

            logger.info(
                "No ATS/career-page/JobSpy results for '%s', trying Adzuna aggregator",
                company_name,
            )
            all_jobs = await search_jobs_by_company(
                company_name, location_hint=location_hint
            )

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

        Uses vector search when VECTOR_SEARCH_ENABLED, Claude API when
        AI_MOCK_MODE=false, keyword matching otherwise.
        Returns jobs with relevance >= 50, sorted by score descending.
        """
        if not jobs or not target_role:
            return []

        # Vector search path
        if settings.VECTOR_SEARCH_ENABLED:
            try:
                company = jobs[0].get("company", "") if jobs else ""
                result = await _vector_match_jobs(jobs, target_role, company)
                if result:
                    return result
            except Exception:
                logger.exception("Vector job match failed, falling back")

        if settings.AI_MOCK_MODE:
            return self._mock_match_jobs(jobs, target_role, target_seniority)

        return await self._ai_match_jobs(jobs, target_role, target_seniority)

    # Level-synonym groups: roles at similar organizational levels.
    # When a target role contains one of these words, titles containing
    # any word in the same group get partial credit.
    _LEVEL_SYNONYMS: dict[str, set[str]] = {
        "manager": {"manager", "director", "head", "lead", "vp"},
        "director": {"director", "manager", "head", "vp", "lead"},
        "head": {"head", "director", "manager", "vp", "lead"},
        "vp": {"vp", "director", "head", "manager"},
        "lead": {"lead", "manager", "head", "director"},
        "engineer": {"engineer", "developer", "programmer", "swe"},
        "developer": {"developer", "engineer", "programmer"},
        "designer": {"designer", "ux", "ui"},
        "analyst": {"analyst", "associate", "coordinator"},
        # Commercial / go-to-market roles
        "sales": {
            "sales",
            "business development",
            "bd",
            "account",
            "commercial",
            "revenue",
        },
        "account": {"account", "sales", "client", "customer", "relationship"},
        "business": {"business", "sales", "commercial", "strategy", "operations"},
        "marketing": {"marketing", "growth", "brand", "communications", "content"},
        # Operations / support roles
        "product": {"product", "program", "project"},
        "operations": {"operations", "ops", "logistics", "supply chain"},
        "finance": {"finance", "accounting", "treasury", "controller"},
        "recruiter": {"recruiter", "talent", "hiring", "people"},
    }

    def _mock_match_jobs(
        self,
        jobs: list[dict],
        target_role: str,
        target_seniority: str | None = None,
    ) -> list[dict]:
        """Mock role matching using keyword overlap + level-synonym expansion."""
        role_words = set(target_role.lower().split())
        seniority_words = (
            set(target_seniority.lower().split()) if target_seniority else set()
        )

        # Build expanded set: for each role word, add its level synonyms
        expanded_words: set[str] = set()
        for w in role_words:
            synonyms = self._LEVEL_SYNONYMS.get(w)
            if synonyms:
                expanded_words |= synonyms

        scored: list[dict] = []
        for job in jobs:
            title = job.get("title", "").lower()
            # Strip punctuation so "Manager," matches "manager"
            title_words = set(re.sub(r"[^\w\s-]", " ", title).split())

            # Score each role word: 1.0 for exact match, 0.7 for synonym
            coverage = 0.0
            for w in role_words:
                if w in title_words:
                    coverage += 1.0
                elif self._LEVEL_SYNONYMS.get(w, set()) & title_words:
                    coverage += 0.7

            # Substring fallback (e.g. "engineer" in "reengineering")
            if coverage == 0 and any(w in title for w in role_words):
                coverage = 0.5

            if coverage == 0:
                continue

            seniority_overlap = (
                len(seniority_words & title_words) if seniority_words else 0
            )

            score = min(
                100,
                int((coverage / max(len(role_words), 1)) * 80 + seniority_overlap * 20),
            )
            if score >= 25:
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
        from app.utils.anthropic_client import get_async_client
        from app.utils.rate_limiter import acquire_slot, release_slot

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

Scoring guide:
- 80-100: Same role or very close variant (e.g. "General Manager" ↔ "General Manager, APAC")
- 60-79: Same job family or function (e.g. "General Manager" ↔ "Director of Operations", "Head of Business")
- 50-59: Related level but different function (e.g. "General Manager" ↔ "Product Manager")
- Below 50: Different role or level entirely (e.g. "General Manager" ↔ "Software Engineer")

Prioritize job family closeness over shared keywords. "Director of Operations" is closer to "General Manager" than "Product Manager" despite sharing fewer words.

JOB TITLES:
{json.dumps(titles, indent=2)}

Return a JSON array of objects with "index" (integer) and "score" (integer 0-100).
Only include jobs scoring >= 50. Return ONLY the JSON array."""

        try:
            client = get_async_client()
            used_redis = await acquire_slot("anthropic")
            try:
                message = await client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=1024,
                    messages=[{"role": "user", "content": prompt}],
                )
            finally:
                await release_slot("anthropic", used_redis)
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

    def filter_and_rank_jobs(
        self,
        jobs: list[dict],
        target_role: str,
        target_seniority: str | None = None,
        target_locations: list[str] | None = None,
        open_to_remote: bool = True,
    ) -> list[dict]:
        """Filter by location/seniority and rank jobs by composite fit score.

        Each job should already have 'role_relevance' from match_jobs_to_role().
        Returns all scored jobs sorted by fit_score descending.
        """
        if not jobs:
            return []

        # Seniority keywords in rough order
        _SENIORITY_LEVELS = {
            "intern",
            "junior",
            "mid",
            "senior",
            "staff",
            "principal",
            "lead",
            "manager",
            "director",
            "vp",
            "c-level",
        }

        # Pre-compute location terms for matching
        loc_terms = (
            [loc.strip().lower() for loc in target_locations if loc.strip()]
            if target_locations
            else []
        )
        seniority_lower = target_seniority.strip().lower() if target_seniority else None

        scored: list[dict] = []
        for job in jobs:
            title_lower = job.get("title", "").lower()
            job_location = (job.get("location") or "").lower()
            is_remote = job.get("is_remote", False)
            role_relevance = job.get("role_relevance", 0)

            # --- Location tagging (soft: tag, don't hard-filter) ---
            in_target_region = False
            if loc_terms:
                if not job_location:
                    in_target_region = False
                elif any(term in job_location for term in loc_terms) or (
                    is_remote and open_to_remote
                ):
                    in_target_region = True

            # --- Location bonus ---
            location_bonus = 0
            if in_target_region:
                location_bonus = 20
            elif is_remote and open_to_remote:
                location_bonus = 5

            # --- Seniority bonus ---
            seniority_bonus = 0
            if seniority_lower:
                if seniority_lower in title_lower:
                    seniority_bonus = 30
                elif any(
                    level in title_lower
                    for level in _SENIORITY_LEVELS
                    if level != seniority_lower
                ):
                    seniority_bonus = -20

            fit_score = role_relevance + location_bonus + seniority_bonus
            scored.append(
                {
                    **job,
                    "fit_score": max(0, fit_score),
                    "in_target_region": in_target_region,
                }
            )

        scored.sort(key=lambda x: (-x["in_target_region"], -x["fit_score"]))
        return scored
