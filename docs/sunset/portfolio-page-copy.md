# WarmPath — Portfolio

## What I Built

WarmPath was a referral marketplace I built and operated from 2025 to
2026. The thesis: cold job applications convert at 1-3%, but employee
referrals convert at 10-40%. Nobody owned the "get me referred" workflow.

WarmPath operated as a two-sided marketplace. Job seekers paid to search
networks they didn't have. Network holders — employees at desirable
companies — uploaded their LinkedIn connections in exchange for credits
and help capturing the referral bonuses their employers already offered
($2-10K per successful hire) that they were leaving on the table.

The core technical challenge was privacy. Contacts in a network holder's
vault never consented to being on the platform. The architecture solved
this with two tiers: a private vault (full data, user-only access) and an
anonymized marketplace index (company + role level + department + connection
strength only). Identity was only revealed when the network holder actively
approved an intro request.

## Technical Highlights

- **Two-tier privacy architecture** with consent gates at every data
  boundary. Contacts never exposed to strangers without explicit
  network-holder approval.
- **Cultural context engine** — AI-generated intro messages adapt to
  the contact's location, company culture, and relationship type.
  Multi-step sequencing (warm-up, explore, ask) for relationship-first
  cultures; direct asks with tone variants for direct cultures.
- **Six specialist AI agent teams + Chief of Staff supervisor** built on
  LangGraph and Claude SDK. Engineering, Data, Product, Ops, Finance, and
  GTM teams each with 4-5 specialist agents running daily scans, generating
  briefs, and surfacing operational insights. Trust model (Observer,
  Recommender, Contributor, Deployer), daily cost guard with Haiku
  fallback, auto-repair pipeline.
- **Unified Memory Service** — hybrid Postgres (BM25 tsvector GIN index) +
  Qdrant (vector embeddings) retrieval with temporal decay and MMR
  re-ranking. Consumed by all 6 agent teams + Claude Code sessions.
- **Multi-provider AI privacy hardening** — contact names and emails never
  sent to external AI providers. Only company names and job titles cross
  the boundary.
- **47 database tables, 3,100+ tests, 4 months of focused build.**

## The Agent Framework

The agent system is arguably the most interesting part of the codebase.
It's a real multi-team AI orchestration framework that ran in production,
not a toy demo. See the
[examples](https://github.com/Rovik/warmpath-agents/tree/master/examples)
directory for actual outputs from the agents analyzing the WarmPath codebase.

[View warmpath-agents on GitHub](https://github.com/Rovik/warmpath-agents)

## Why I Sunset It

WarmPath was technically complete and operational, but it needs full-time
user acquisition work to grow — and I didn't have the time to invest in
that. Rather than let the code rot in a private repo, I sunset the live
product and released both the application and the agent framework as open
source.

## Source Code

- **[warmpath](https://github.com/Rovik/warmpath)** — the full product
  (FastAPI + React + PostgreSQL, 47 tables, 3,100+ tests)
- **[warmpath-agents](https://github.com/Rovik/warmpath-agents)** — the
  agent framework (6 teams + CoS, LangGraph, memory service, MCP server)

Both repos are Apache-2.0 licensed.
