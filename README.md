# WarmPath

> **This project was sunset on April 28, 2026.** The code is preserved here
> for reference and learning. PRs and issues will not be reviewed.

WarmPath was a referral marketplace platform that helped job seekers get
employee referrals instead of applying cold. It operated as a two-sided
marketplace: job seekers paid to access networks they didn't have, while
network holders uploaded their LinkedIn connections in exchange for credits
and help capturing referral bonuses.

## What's Interesting Here

- **Two-tier privacy architecture** — private vault (full data, user-only)
  + anonymized marketplace index. Contact identity only revealed through
  explicit network holder approval.
- **Cultural context engine** — AI-generated intro messages adapt to contact
  location, company culture, and relationship type.
- **47 database tables**, 3,100+ tests, 4 months of build.
- **Multi-provider AI pipeline** — Claude, Gemini, OpenAI, Groq with
  privacy hardening (contact PII never crosses to external AI).
- **On-platform intro relay** — email relay via Resend with delivery
  tracking and credit-on-delivery.

## Sister Repo

The agent framework that monitored and analyzed this product is in a
separate repo: **[warmpath-agents](https://github.com/Rovik/warmpath-agents)**.

## Quick Start

```bash
# Requires Docker
cp .env.dev.example .env.dev
make dev        # Start Postgres + Redis + API + Worker + Frontend
make seed       # Populate with test data
make test       # Run 3,100+ tests
```

Visit `http://localhost:5173` for the frontend.

## Tech Stack

- **Backend:** Python 3.11+ / FastAPI / SQLAlchemy / Alembic
- **Frontend:** React 19 / Vite / Tailwind CSS 4
- **Database:** PostgreSQL 15+ / Redis 7
- **AI:** Anthropic Claude API
- **Auth:** Clerk
- **Task Queue:** Celery + Redis

## For forks and self-maintainers

- [CONTRIBUTING.md](CONTRIBUTING.md) — local dev setup, tests, lint
- [SECURITY.md](SECURITY.md) — security posture (no patches will ship)
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — Contributor Covenant v2.1
- [ARCHITECTURE.md](ARCHITECTURE.md) — system design overview
- [frontend/README.md](frontend/README.md) — frontend setup and scripts

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
