"""GTM service layer — CRUD + business logic for competitors, pricing, partnerships, experiments."""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gtm import (
    CompetitorProfile,
    GTMExperiment,
    PartnershipOpportunity,
    PricingBenchmark,
)
from app.utils.exceptions import NotFoundError, ValidationError

# ---------------------------------------------------------------------------
# Validation sets
# ---------------------------------------------------------------------------

VALID_CATEGORIES = {"direct", "indirect", "adjacent"}
VALID_THREAT_LEVELS = {"low", "medium", "high", "critical"}
VALID_PRODUCT_CATEGORIES = {
    "referral_platform",
    "job_board",
    "networking",
    "hr_tech",
    "career_coaching",
}
VALID_PRICING_MODELS = {
    "freemium",
    "subscription",
    "usage",
    "hybrid",
    "enterprise_only",
}
VALID_PARTNER_TYPES = {
    "bootcamp",
    "university",
    "coach",
    "association",
    "corporate",
    "strategic",
}
VALID_STAGES = {
    "identified",
    "outreach",
    "conversation",
    "proposal",
    "negotiation",
    "signed",
    "lost",
}
STAGE_ORDER = [
    "identified",
    "outreach",
    "conversation",
    "proposal",
    "negotiation",
    "signed",
]
VALID_LEGAL_STATUSES = {"not_required", "pending", "approved", "blocked"}
VALID_EXPERIMENT_TYPES = {
    "pricing",
    "messaging",
    "channel",
    "landing_page",
    "onboarding",
}
VALID_EXPERIMENT_STATUSES = {"draft", "running", "paused", "completed", "analyzed"}

# Terminal partnership stages — cannot advance from these
_TERMINAL_STAGES = {"signed", "lost"}

# WarmPath midpoint price for percentile calculation
_WARMPATH_MIDPOINT = Decimal("25.00")


# ===========================================================================
# Competitors
# ===========================================================================


async def list_competitors(
    db: AsyncSession,
    *,
    category: str | None = None,
    threat_level: str | None = None,
) -> list[CompetitorProfile]:
    """List all active competitors with optional filters."""
    query = select(CompetitorProfile).where(CompetitorProfile.deleted_at.is_(None))
    if category is not None:
        if category not in VALID_CATEGORIES:
            raise ValidationError(f"category must be one of {VALID_CATEGORIES}")
        query = query.where(CompetitorProfile.category == category)
    if threat_level is not None:
        if threat_level not in VALID_THREAT_LEVELS:
            raise ValidationError(f"threat_level must be one of {VALID_THREAT_LEVELS}")
        query = query.where(CompetitorProfile.threat_level == threat_level)
    query = query.order_by(CompetitorProfile.name)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_competitor(
    db: AsyncSession, competitor_id: uuid.UUID
) -> CompetitorProfile | None:
    """Get a single competitor by ID (soft-delete filtered)."""
    result = await db.execute(
        select(CompetitorProfile).where(
            CompetitorProfile.id == competitor_id,
            CompetitorProfile.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def create_competitor(
    db: AsyncSession,
    *,
    name: str,
    category: str,
    domain: str | None = None,
    features: dict | None = None,
    pricing: dict | None = None,
    positioning: dict | None = None,
    target_market: str | None = None,
    funding_stage: str | None = None,
    employee_count: int | None = None,
    strengths: dict | None = None,
    weaknesses: dict | None = None,
    threat_level: str = "medium",
    source_urls: dict | None = None,
) -> CompetitorProfile:
    """Create a new competitor profile."""
    if category not in VALID_CATEGORIES:
        raise ValidationError(f"category must be one of {VALID_CATEGORIES}")
    if threat_level not in VALID_THREAT_LEVELS:
        raise ValidationError(f"threat_level must be one of {VALID_THREAT_LEVELS}")

    competitor = CompetitorProfile(
        name=name,
        domain=domain,
        category=category,
        features=features,
        pricing=pricing,
        positioning=positioning,
        target_market=target_market,
        funding_stage=funding_stage,
        employee_count=employee_count,
        strengths=strengths,
        weaknesses=weaknesses,
        threat_level=threat_level,
        source_urls=source_urls,
    )
    db.add(competitor)
    await db.flush()
    return competitor


async def update_competitor(
    db: AsyncSession,
    competitor_id: uuid.UUID,
    **kwargs: object,
) -> CompetitorProfile:
    """Update fields on an existing competitor."""
    competitor = await get_competitor(db, competitor_id)
    if competitor is None:
        raise NotFoundError(f"Competitor {competitor_id} not found")

    if "category" in kwargs and kwargs["category"] not in VALID_CATEGORIES:
        raise ValidationError(f"category must be one of {VALID_CATEGORIES}")
    if "threat_level" in kwargs and kwargs["threat_level"] not in VALID_THREAT_LEVELS:
        raise ValidationError(f"threat_level must be one of {VALID_THREAT_LEVELS}")

    allowed = {
        "name",
        "domain",
        "category",
        "features",
        "pricing",
        "positioning",
        "target_market",
        "funding_stage",
        "employee_count",
        "strengths",
        "weaknesses",
        "threat_level",
        "last_scraped_at",
        "source_urls",
    }
    for key, value in kwargs.items():
        if key in allowed:
            setattr(competitor, key, value)

    await db.flush()
    return competitor


async def soft_delete_competitor(
    db: AsyncSession, competitor_id: uuid.UUID
) -> CompetitorProfile:
    """Soft-delete a competitor by setting deleted_at."""
    competitor = await get_competitor(db, competitor_id)
    if competitor is None:
        raise NotFoundError(f"Competitor {competitor_id} not found")
    competitor.deleted_at = datetime.now(timezone.utc)
    await db.flush()
    return competitor


async def get_competitor_matrix(db: AsyncSession) -> dict:
    """Build a feature comparison matrix across all active competitors.

    Returns:
        {
            "competitors": [{"id", "name", "domain", "category", "features", "pricing", "threat_level"}],
            "all_features": sorted list of every feature key across all competitors,
            "matrix": {competitor_name: {feature: present_bool}},
        }
    """
    competitors = await list_competitors(db)
    all_features: set[str] = set()
    matrix: dict[str, dict[str, bool]] = {}

    for c in competitors:
        feats = c.features or {}
        feature_keys = set(feats.keys()) if isinstance(feats, dict) else set()
        all_features.update(feature_keys)

    sorted_features = sorted(all_features)

    for c in competitors:
        feats = c.features or {}
        feature_keys = set(feats.keys()) if isinstance(feats, dict) else set()
        matrix[c.name] = {f: f in feature_keys for f in sorted_features}

    return {
        "competitors": [
            {
                "id": str(c.id),
                "name": c.name,
                "domain": c.domain,
                "category": c.category,
                "features": c.features,
                "pricing": c.pricing,
                "threat_level": c.threat_level,
            }
            for c in competitors
        ],
        "all_features": sorted_features,
        "matrix": matrix,
    }


# ===========================================================================
# Pricing Benchmarks
# ===========================================================================


async def list_benchmarks(
    db: AsyncSession,
    *,
    product_category: str | None = None,
    pricing_model: str | None = None,
) -> list[PricingBenchmark]:
    """List all active pricing benchmarks with optional filters."""
    query = select(PricingBenchmark).where(PricingBenchmark.deleted_at.is_(None))
    if product_category is not None:
        if product_category not in VALID_PRODUCT_CATEGORIES:
            raise ValidationError(
                f"product_category must be one of {VALID_PRODUCT_CATEGORIES}"
            )
        query = query.where(PricingBenchmark.product_category == product_category)
    if pricing_model is not None:
        if pricing_model not in VALID_PRICING_MODELS:
            raise ValidationError(
                f"pricing_model must be one of {VALID_PRICING_MODELS}"
            )
        query = query.where(PricingBenchmark.pricing_model == pricing_model)
    query = query.order_by(PricingBenchmark.company_name)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_benchmark(
    db: AsyncSession, benchmark_id: uuid.UUID
) -> PricingBenchmark | None:
    """Get a single pricing benchmark by ID (soft-delete filtered)."""
    result = await db.execute(
        select(PricingBenchmark).where(
            PricingBenchmark.id == benchmark_id,
            PricingBenchmark.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def create_benchmark(
    db: AsyncSession,
    *,
    company_name: str,
    product_category: str,
    pricing_model: str,
    domain: str | None = None,
    tiers: dict | None = None,
    free_tier_exists: bool | None = None,
    lowest_paid_price: float | None = None,
    enterprise_available: bool | None = None,
    source_url: str | None = None,
    scraped_at: datetime | None = None,
    notes: str | None = None,
) -> PricingBenchmark:
    """Create a new pricing benchmark entry."""
    if product_category not in VALID_PRODUCT_CATEGORIES:
        raise ValidationError(
            f"product_category must be one of {VALID_PRODUCT_CATEGORIES}"
        )
    if pricing_model not in VALID_PRICING_MODELS:
        raise ValidationError(f"pricing_model must be one of {VALID_PRICING_MODELS}")

    benchmark = PricingBenchmark(
        company_name=company_name,
        domain=domain,
        product_category=product_category,
        pricing_model=pricing_model,
        tiers=tiers,
        free_tier_exists=free_tier_exists,
        lowest_paid_price=lowest_paid_price,
        enterprise_available=enterprise_available,
        source_url=source_url,
        scraped_at=scraped_at,
        notes=notes,
    )
    db.add(benchmark)
    await db.flush()
    return benchmark


async def update_benchmark(
    db: AsyncSession,
    benchmark_id: uuid.UUID,
    **kwargs: object,
) -> PricingBenchmark:
    """Update fields on an existing pricing benchmark."""
    benchmark = await get_benchmark(db, benchmark_id)
    if benchmark is None:
        raise NotFoundError(f"Benchmark {benchmark_id} not found")

    if (
        "product_category" in kwargs
        and kwargs["product_category"] not in VALID_PRODUCT_CATEGORIES
    ):
        raise ValidationError(
            f"product_category must be one of {VALID_PRODUCT_CATEGORIES}"
        )
    if (
        "pricing_model" in kwargs
        and kwargs["pricing_model"] not in VALID_PRICING_MODELS
    ):
        raise ValidationError(f"pricing_model must be one of {VALID_PRICING_MODELS}")

    allowed = {
        "company_name",
        "domain",
        "product_category",
        "pricing_model",
        "tiers",
        "free_tier_exists",
        "lowest_paid_price",
        "enterprise_available",
        "source_url",
        "scraped_at",
        "notes",
    }
    for key, value in kwargs.items():
        if key in allowed:
            setattr(benchmark, key, value)

    await db.flush()
    return benchmark


async def soft_delete_benchmark(
    db: AsyncSession, benchmark_id: uuid.UUID
) -> PricingBenchmark:
    """Soft-delete a pricing benchmark."""
    benchmark = await get_benchmark(db, benchmark_id)
    if benchmark is None:
        raise NotFoundError(f"Benchmark {benchmark_id} not found")
    benchmark.deleted_at = datetime.now(timezone.utc)
    await db.flush()
    return benchmark


async def get_pricing_summary(db: AsyncSession) -> dict:
    """Compute pricing analytics across all active benchmarks.

    Returns:
        {
            "total_benchmarks": int,
            "avg_lowest_paid_price": float | None,
            "model_distribution": {model: count},
            "category_distribution": {category: count},
            "warmpath_percentile": float | None,  # % of products priced above $25/mo
        }
    """
    benchmarks = await list_benchmarks(db)

    if not benchmarks:
        return {
            "total_benchmarks": 0,
            "avg_lowest_paid_price": None,
            "model_distribution": {},
            "category_distribution": {},
            "warmpath_percentile": None,
        }

    # Compute average lowest paid price
    prices = [
        Decimal(str(b.lowest_paid_price))
        for b in benchmarks
        if b.lowest_paid_price is not None
    ]
    avg_price = float(sum(prices) / len(prices)) if prices else None

    # Model distribution
    model_dist: dict[str, int] = {}
    for b in benchmarks:
        model_dist[b.pricing_model] = model_dist.get(b.pricing_model, 0) + 1

    # Category distribution
    cat_dist: dict[str, int] = {}
    for b in benchmarks:
        cat_dist[b.product_category] = cat_dist.get(b.product_category, 0) + 1

    # WarmPath percentile: what % of tracked products are priced ABOVE $25/mo
    # Higher percentile = WarmPath is more affordable relative to market
    if prices:
        above_warmpath = sum(1 for p in prices if p > _WARMPATH_MIDPOINT)
        percentile = round((above_warmpath / len(prices)) * 100, 1)
    else:
        percentile = None

    return {
        "total_benchmarks": len(benchmarks),
        "avg_lowest_paid_price": avg_price,
        "model_distribution": model_dist,
        "category_distribution": cat_dist,
        "warmpath_percentile": percentile,
    }


# ===========================================================================
# Partnerships
# ===========================================================================


async def list_partnerships(
    db: AsyncSession,
    *,
    stage: str | None = None,
    partner_type: str | None = None,
    overdue: bool = False,
) -> list[PartnershipOpportunity]:
    """List active partnerships with optional filters.

    Args:
        stage: Filter by pipeline stage.
        partner_type: Filter by partner type.
        overdue: If True, only return partnerships with next_action_date < today.
    """
    query = select(PartnershipOpportunity).where(
        PartnershipOpportunity.deleted_at.is_(None)
    )
    if stage is not None:
        if stage not in VALID_STAGES:
            raise ValidationError(f"stage must be one of {VALID_STAGES}")
        query = query.where(PartnershipOpportunity.stage == stage)
    if partner_type is not None:
        if partner_type not in VALID_PARTNER_TYPES:
            raise ValidationError(f"partner_type must be one of {VALID_PARTNER_TYPES}")
        query = query.where(PartnershipOpportunity.partner_type == partner_type)
    if overdue:
        today = date.today()
        query = query.where(PartnershipOpportunity.next_action_date < today)

    query = query.order_by(PartnershipOpportunity.partner_name)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_partnership(
    db: AsyncSession, partnership_id: uuid.UUID
) -> PartnershipOpportunity | None:
    """Get a single partnership by ID (soft-delete filtered)."""
    result = await db.execute(
        select(PartnershipOpportunity).where(
            PartnershipOpportunity.id == partnership_id,
            PartnershipOpportunity.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def create_partnership(
    db: AsyncSession,
    *,
    partner_name: str,
    partner_type: str,
    partner_domain: str | None = None,
    stage: str = "identified",
    contact_name: str | None = None,
    contact_email: str | None = None,
    estimated_users: int | None = None,
    estimated_monthly_revenue: float | None = None,
    notes: dict | None = None,
    legal_review_status: str = "not_required",
    next_action: str | None = None,
    next_action_date: date | None = None,
    created_by: uuid.UUID | None = None,
) -> PartnershipOpportunity:
    """Create a new partnership opportunity."""
    if partner_type not in VALID_PARTNER_TYPES:
        raise ValidationError(f"partner_type must be one of {VALID_PARTNER_TYPES}")
    if stage not in VALID_STAGES:
        raise ValidationError(f"stage must be one of {VALID_STAGES}")
    if legal_review_status not in VALID_LEGAL_STATUSES:
        raise ValidationError(
            f"legal_review_status must be one of {VALID_LEGAL_STATUSES}"
        )

    partnership = PartnershipOpportunity(
        partner_name=partner_name,
        partner_domain=partner_domain,
        partner_type=partner_type,
        stage=stage,
        contact_name=contact_name,
        contact_email=contact_email,
        estimated_users=estimated_users,
        estimated_monthly_revenue=estimated_monthly_revenue,
        notes=notes,
        legal_review_status=legal_review_status,
        next_action=next_action,
        next_action_date=next_action_date,
        created_by=created_by,
    )
    db.add(partnership)
    await db.flush()
    return partnership


async def update_partnership(
    db: AsyncSession,
    partnership_id: uuid.UUID,
    **kwargs: object,
) -> PartnershipOpportunity:
    """Update fields on an existing partnership."""
    partnership = await get_partnership(db, partnership_id)
    if partnership is None:
        raise NotFoundError(f"Partnership {partnership_id} not found")

    if "partner_type" in kwargs and kwargs["partner_type"] not in VALID_PARTNER_TYPES:
        raise ValidationError(f"partner_type must be one of {VALID_PARTNER_TYPES}")
    if "stage" in kwargs and kwargs["stage"] not in VALID_STAGES:
        raise ValidationError(f"stage must be one of {VALID_STAGES}")
    if (
        "legal_review_status" in kwargs
        and kwargs["legal_review_status"] not in VALID_LEGAL_STATUSES
    ):
        raise ValidationError(
            f"legal_review_status must be one of {VALID_LEGAL_STATUSES}"
        )

    allowed = {
        "partner_name",
        "partner_domain",
        "partner_type",
        "stage",
        "contact_name",
        "contact_email",
        "estimated_users",
        "estimated_monthly_revenue",
        "notes",
        "legal_review_status",
        "next_action",
        "next_action_date",
        "lost_reason",
    }
    stage_changed = False
    for key, value in kwargs.items():
        if key in allowed:
            if key == "stage" and value != partnership.stage:
                stage_changed = True
            setattr(partnership, key, value)

    if stage_changed:
        partnership.stage_changed_at = datetime.now(timezone.utc)

    await db.flush()
    return partnership


async def advance_partnership(
    db: AsyncSession, partnership_id: uuid.UUID
) -> PartnershipOpportunity:
    """Move a partnership to the next stage in the pipeline.

    Raises ValueError if the partnership is in a terminal stage (signed/lost).
    """
    partnership = await get_partnership(db, partnership_id)
    if partnership is None:
        raise NotFoundError(f"Partnership {partnership_id} not found")

    if partnership.stage in _TERMINAL_STAGES:
        raise ValidationError(
            f"Cannot advance from terminal stage '{partnership.stage}'"
        )

    current_index = STAGE_ORDER.index(partnership.stage)
    next_stage = STAGE_ORDER[current_index + 1]

    partnership.stage = next_stage
    partnership.stage_changed_at = datetime.now(timezone.utc)
    await db.flush()
    return partnership


async def lose_partnership(
    db: AsyncSession,
    partnership_id: uuid.UUID,
    *,
    lost_reason: str,
) -> PartnershipOpportunity:
    """Mark a partnership as lost with a reason."""
    partnership = await get_partnership(db, partnership_id)
    if partnership is None:
        raise NotFoundError(f"Partnership {partnership_id} not found")

    partnership.stage = "lost"
    partnership.lost_reason = lost_reason
    partnership.stage_changed_at = datetime.now(timezone.utc)
    await db.flush()
    return partnership


async def soft_delete_partnership(
    db: AsyncSession, partnership_id: uuid.UUID
) -> PartnershipOpportunity:
    """Soft-delete a partnership by setting deleted_at."""
    partnership = await get_partnership(db, partnership_id)
    if partnership is None:
        raise NotFoundError(f"Partnership {partnership_id} not found")
    partnership.deleted_at = datetime.now(timezone.utc)
    await db.flush()
    return partnership


async def get_pipeline_metrics(db: AsyncSession) -> dict:
    """Compute partnership pipeline analytics.

    Returns:
        {
            "deals_per_stage": {stage: count},
            "total_active": int,
            "stuck_deals": [{"id", "partner_name", "stage", "days_in_stage"}],
            "conversion_rate": float | None,  # signed / (signed + lost)
            "total_estimated_monthly_revenue": float,
        }
    """
    all_partnerships = await list_partnerships(db)

    # Deals per stage
    deals_per_stage: dict[str, int] = {s: 0 for s in VALID_STAGES}
    for p in all_partnerships:
        deals_per_stage[p.stage] = deals_per_stage.get(p.stage, 0) + 1

    # Stuck deals: not in a terminal stage and stage_changed_at > 30 days ago
    now = datetime.now(timezone.utc)
    stuck_threshold = now - timedelta(days=30)
    stuck_deals = []
    for p in all_partnerships:
        if p.stage in _TERMINAL_STAGES:
            continue
        if p.stage_changed_at is not None:
            # Ensure timezone-aware comparison (SQLite stores naive datetimes)
            sca = p.stage_changed_at
            if sca.tzinfo is None:
                sca = sca.replace(tzinfo=timezone.utc)
            if sca < stuck_threshold:
                days = (now - sca).days
                stuck_deals.append(
                    {
                        "id": str(p.id),
                        "partner_name": p.partner_name,
                        "stage": p.stage,
                        "days_in_stage": days,
                    }
                )

    # Conversion rate: signed / (signed + lost)
    signed = deals_per_stage.get("signed", 0)
    lost = deals_per_stage.get("lost", 0)
    terminal_total = signed + lost
    conversion_rate = round(signed / terminal_total, 3) if terminal_total > 0 else None

    # Total estimated monthly revenue (active, non-terminal)
    total_emr = sum(
        float(p.estimated_monthly_revenue)
        for p in all_partnerships
        if p.estimated_monthly_revenue is not None and p.stage not in _TERMINAL_STAGES
    )

    return {
        "deals_per_stage": deals_per_stage,
        "total_active": len(
            [p for p in all_partnerships if p.stage not in _TERMINAL_STAGES]
        ),
        "stuck_deals": stuck_deals,
        "conversion_rate": conversion_rate,
        "total_estimated_monthly_revenue": total_emr,
    }


# ===========================================================================
# Experiments
# ===========================================================================


async def list_experiments(
    db: AsyncSession,
    *,
    status: str | None = None,
    experiment_type: str | None = None,
) -> list[GTMExperiment]:
    """List all active experiments with optional filters."""
    query = select(GTMExperiment).where(GTMExperiment.deleted_at.is_(None))
    if status is not None:
        if status not in VALID_EXPERIMENT_STATUSES:
            raise ValidationError(f"status must be one of {VALID_EXPERIMENT_STATUSES}")
        query = query.where(GTMExperiment.status == status)
    if experiment_type is not None:
        if experiment_type not in VALID_EXPERIMENT_TYPES:
            raise ValidationError(
                f"experiment_type must be one of {VALID_EXPERIMENT_TYPES}"
            )
        query = query.where(GTMExperiment.experiment_type == experiment_type)
    query = query.order_by(GTMExperiment.name)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_experiment(
    db: AsyncSession, experiment_id: uuid.UUID
) -> GTMExperiment | None:
    """Get a single experiment by ID (soft-delete filtered)."""
    result = await db.execute(
        select(GTMExperiment).where(
            GTMExperiment.id == experiment_id,
            GTMExperiment.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def create_experiment(
    db: AsyncSession,
    *,
    name: str,
    experiment_type: str,
    hypothesis: str | None = None,
    status: str = "draft",
    variants: dict | None = None,
    metrics: dict | None = None,
    target_sample_size: int | None = None,
    created_by: uuid.UUID | None = None,
) -> GTMExperiment:
    """Create a new GTM experiment."""
    if experiment_type not in VALID_EXPERIMENT_TYPES:
        raise ValidationError(
            f"experiment_type must be one of {VALID_EXPERIMENT_TYPES}"
        )
    if status not in VALID_EXPERIMENT_STATUSES:
        raise ValidationError(f"status must be one of {VALID_EXPERIMENT_STATUSES}")

    experiment = GTMExperiment(
        name=name,
        hypothesis=hypothesis,
        experiment_type=experiment_type,
        status=status,
        variants=variants,
        metrics=metrics,
        target_sample_size=target_sample_size,
        created_by=created_by,
    )
    db.add(experiment)
    await db.flush()
    return experiment


async def update_experiment(
    db: AsyncSession,
    experiment_id: uuid.UUID,
    **kwargs: object,
) -> GTMExperiment:
    """Update fields on an existing experiment."""
    experiment = await get_experiment(db, experiment_id)
    if experiment is None:
        raise NotFoundError(f"Experiment {experiment_id} not found")

    if (
        "experiment_type" in kwargs
        and kwargs["experiment_type"] not in VALID_EXPERIMENT_TYPES
    ):
        raise ValidationError(
            f"experiment_type must be one of {VALID_EXPERIMENT_TYPES}"
        )

    allowed = {
        "name",
        "hypothesis",
        "experiment_type",
        "variants",
        "metrics",
        "target_sample_size",
    }
    for key, value in kwargs.items():
        if key in allowed:
            setattr(experiment, key, value)

    await db.flush()
    return experiment


async def start_experiment(db: AsyncSession, experiment_id: uuid.UUID) -> GTMExperiment:
    """Start an experiment (transition from draft to running).

    Raises ValueError if the experiment is not in draft status.
    """
    experiment = await get_experiment(db, experiment_id)
    if experiment is None:
        raise NotFoundError(f"Experiment {experiment_id} not found")

    if experiment.status != "draft":
        raise ValidationError(
            f"Can only start experiments in 'draft' status, current: '{experiment.status}'"
        )

    experiment.status = "running"
    experiment.started_at = datetime.now(timezone.utc)
    await db.flush()
    return experiment


async def complete_experiment(
    db: AsyncSession,
    experiment_id: uuid.UUID,
    *,
    results: dict | None = None,
    conclusion: str | None = None,
    recommendation: str | None = None,
) -> GTMExperiment:
    """Complete an experiment (transition from running/paused to completed).

    Records results, conclusion, recommendation, and sets ended_at.
    Raises ValueError if the experiment is not in running or paused status.
    """
    experiment = await get_experiment(db, experiment_id)
    if experiment is None:
        raise NotFoundError(f"Experiment {experiment_id} not found")

    if experiment.status not in ("running", "paused"):
        raise ValidationError(
            f"Can only complete experiments in 'running' or 'paused' status, "
            f"current: '{experiment.status}'"
        )

    experiment.status = "completed"
    experiment.ended_at = datetime.now(timezone.utc)
    if results is not None:
        experiment.results = results
    if conclusion is not None:
        experiment.conclusion = conclusion
    if recommendation is not None:
        experiment.recommendation = recommendation

    await db.flush()
    return experiment


async def soft_delete_experiment(
    db: AsyncSession, experiment_id: uuid.UUID
) -> GTMExperiment:
    """Soft-delete an experiment by setting deleted_at."""
    experiment = await get_experiment(db, experiment_id)
    if experiment is None:
        raise NotFoundError(f"Experiment {experiment_id} not found")
    experiment.deleted_at = datetime.now(timezone.utc)
    await db.flush()
    return experiment
