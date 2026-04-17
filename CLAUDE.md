# WarmPath — Developer Context

> **Sunset notice:** This project was sunset on April 28, 2026.
> See [README.md](README.md) for background.

This file provides context for AI coding assistants (Claude Code, Copilot, Cursor)
and for the WarmPath agent teams that scan the codebase.

## What This Is

WarmPath was a referral marketplace where job seekers paid to access employee
networks, and network holders earned credits + referral bonuses. Two-sided
marketplace with a privacy-first architecture: contacts never exposed without
explicit network-holder approval.

## Key Architecture Decisions

- **Two-tier privacy**: private vault (full PII, user-only) + anonymized marketplace
  index (company/role/department/strength only). Identity revealed only on approval.
- **Cultural context engine**: AI-generated intro messages adapt to contact location,
  company culture, and relationship type.
- **Six AI agent teams** (LangGraph + Claude SDK): Engineering, Data, Product, Ops,
  Finance, GTM — each with specialist agents running daily scans.
- **Hybrid search**: Postgres BM25 (tsvector GIN) + Qdrant vector embeddings with
  temporal decay and MMR re-ranking.

## Tech Stack

- **Backend**: FastAPI, SQLAlchemy (async), Alembic, Celery + Redis
- **Frontend**: React 18, TypeScript, Tailwind CSS, Vite
- **AI**: Claude (Anthropic), Gemini (Google), GPT-4 (OpenAI)
- **Database**: PostgreSQL (47 tables), Qdrant (vector search)
- **Infra**: Railway (prod), GitHub Actions (CI)

## Repository Layout

See [ARCHITECTURE.md](ARCHITECTURE.md) for the detailed module map.
