# Next Session Prompts — WarmPath Sunset

Copy-paste these into fresh Claude Code sessions to continue the work.

## Session A: Fix seed script + generate agent demos

```
I'm working on the WarmPath sunset/OSS project. Two public repos are already live:
- github.com/rovikrobert/warmpath
- github.com/rovikrobert/warmpath-agents

I need to generate synthetic agent demo outputs for warmpath-agents/examples/.
The seed script (scripts/seed_dev.py) has a bug — it uses relationship_type
values that violate the ck_contacts_relationship_type check constraint on the
contacts table. Fix the seed script, then:

1. Start Docker: `docker compose -f docker-compose.dev.yml up -d db redis`
   (stop native postgres first: `brew services stop postgresql@17`)
2. Run migrations: `DATABASE_URL="[DATABASE_URL_REDACTED]" alembic upgrade head`
3. Run seed: `DATABASE_URL="postgresql+asyncpg://warmpath:warmpath@127.0.0.1:5433/warmpath_dev" REDIS_URL="redis://127.0.0.1:6380/0" python3 -m scripts.seed_dev`
4. Run agent scans against the seeded DB and capture outputs
5. Curate 5-7 example outputs into /tmp/warmpath-agents-oss-source/examples/ as static markdown
6. Eyeball check for PII (no real emails/UUIDs)
7. Commit and push to github.com/rovikrobert/warmpath-agents

The extracted agents repo is at /tmp/warmpath-agents-oss-source.
If it's gone (reboot), re-extract following docs/superpowers/plans/2026-04-12-warmpath-sunset-and-oss.md Task 9.

Design spec: docs/superpowers/specs/2026-04-12-warmpath-sunset-and-oss-design.md
Full plan: docs/superpowers/plans/2026-04-12-warmpath-sunset-and-oss.md
```

## Session B: Day 1 — deploy sunset mode + send emails

```
I'm executing Day 1 of the WarmPath sunset. The runbook is at
docs/sunset/runbook-day-1.md. Follow it step by step.

Key actions:
1. Deploy SUNSET_MODE=true and VITE_SUNSET_MODE=true to Railway
2. Send 9 personal shutdown notes (templates at docs/sunset/personal-note-template.md)
3. Send Resend blast to 18 other users (template at docs/sunset/resend-blast-template.md)
4. Disable Clerk signups
5. Stop Railway services: worker, beat, agent-runtime, mcp-server, cron
6. Verify: banner visible, upload returns 410, intro returns 410

IMPORTANT: Before sending emails, verify the 1 weekly active user identity:
query_sql("SELECT user_id FROM usage_logs WHERE created_at > NOW() - INTERVAL '7 days' GROUP BY user_id")

Design spec: docs/superpowers/specs/2026-04-12-warmpath-sunset-and-oss-design.md
Local origin is now: github.com/rovikrobert/warmpath-original (private)
```

## Session C: Day 14 — shutoff + PII cleanup

```
I'm executing Day 14 of the WarmPath sunset. The runbook is at
docs/sunset/runbook-day-14.md. Follow it step by step.

Key actions:
1. Verify all export requests fulfilled
2. pg_dump → GPG encrypt → upload to 1Password "WarmPath Sunset Archive"
3. Verify decryption round-trip
4. Delete all Railway services (Postgres, Redis, web, frontend)
5. Set up Cloudflare/Vercel redirect: warmpath.majiq.agency → majiq.agency/warmpath
6. PII cleanup: Clerk users, Resend logs, W&B project, Stripe customers,
   Telegram bot, Qdrant collection
7. Git bundle the private repo → GPG → 1Password → delete GitHub repo
8. Local cleanup: rm reports, dumps, playwright files

BEFORE starting: take screenshots of W&B Weave traces, Telegram bot,
and the live product with sunset banner (Task 14 in the plan). These
services get deleted in this session.

Design spec: docs/superpowers/specs/2026-04-12-warmpath-sunset-and-oss-design.md
```

## Session D: Day 44 — destroy snapshots

```
I'm executing Day 44 of the WarmPath sunset. The runbook is at
docs/sunset/runbook-day-44.md.

1. Grep inbox for any export requests in the last 30 days
2. Final decryption test on the DB snapshot
3. Delete warmpath_final_2026-04-28.dump.gpg from 1Password
4. Delete warmpath-final.bundle.gpg from 1Password
5. Verify in 1Password audit log
6. Remove calendar reminder

After this: zero remaining PII. Project complete.
```

## Session E: Update marketing page (optional)

```
I need to update the majiq.agency/warmpath page to be a portfolio page
showing what I built. The copy is already written at
docs/sunset/portfolio-page-copy.md in the warmpath repo.

The marketing site is in a separate repo. Help me adapt the copy
into whatever format that site uses and deploy it.
```
