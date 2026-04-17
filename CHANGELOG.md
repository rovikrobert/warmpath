# Changelog

All notable changes to WarmPath. This project was sunset on April 28, 2026.

## 2026-04-16 — CI Speed & Reproducibility

- Add `requirements-test.lock` (hash-verified, Linux-pinned via `uv pip compile`)
- Add `lock-freshness` CI job blocking stale locks
- Add `setup-python-warmpath` composite action (Python 3.11, optional pip cache)
- Enable uv cache on test/dep-audit, pip cache on lint
- Switch dep-audit to audit the lock instead of floor-bound requirements.txt
- Fix `auto-deps.yml` to regenerate lock after security patches (fail-closed)
- Bump cryptography (46.0.7), langchain-core (1.2.28), python-multipart (0.0.26) for CVEs
- Fix security scanner version-parser for compound specs (`>=x,<y`)
- Fix 7 pre-existing test failures (csv_completion NameError, CLAUDE.md assertion,
  health-check DATABASE_URL, OG middleware status, competitor registry)
- Apply ruff format to 4 drift files

## 2026-04-15 — OSS Hygiene

- Add Apache-2.0 LICENSE, NOTICE, sunset README
- Add SECURITY.md, CODE_OF_CONDUCT.md, CONTRIBUTING.md
- Add `.github/ISSUE_TEMPLATE/archived-project.md` and PR template
- Security: fail closed on unsigned webhooks and missing encryption
- Reliability: improve health signal quality, tighten startup exception handling

## 2026-04-14 — Performance

- Batch N+1 queries in feed generation, contact export, smart-search
- Bounded concurrency for smart-search marketplace queries
- Contact export streaming (memory-efficient CSV generation)

## 2026-04-12 — Sunset Preparation

- Add `SUNSET_MODE` config + 410 Gone on upload and intro endpoints
- Add `SunsetBanner` React component for sunset mode UI
- Add user vault export script for data portability
- Add sunset communication templates and ops runbooks

## 2026-04-10 — Agent System Maturation

- Add confidence field and execution gating for agent findings
- Suppress low-confidence findings in Telegram reports
- Deduplicate N+1 scanners, auto-expire stale decisions
- Stop daily briefs from repeating resolved/identical findings
- Default `/agents/run` to full-scan mode

## 2026-03 — Core Platform

- Feedback modal wired into search results
- Telegram stats command and slash command infrastructure
- Cohort activation: onboarding gate, CSV validation, search redirects
- CSV V2 pipeline: company linking and marketplace regeneration
- Standalone Qdrant keep-alive for Railway Cron
- Tag 84 critical-path smoke tests (4.3s Tier 1)
