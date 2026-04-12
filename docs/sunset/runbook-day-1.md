# Day 1 Runbook (2026-04-14)

## Pre-flight (Gate 1)
- [ ] Personal note drafts reviewed for typos / wrong names
- [ ] Resend blast template rendered in test mode
- [ ] SunsetBanner deployed (VITE_SUNSET_MODE=true on Railway)
- [ ] Calendar reminders set: 2026-04-28 (shutoff), 2026-05-28 (destroy)

## Communications
- [ ] Send 9 personal notes manually (one by one, from personal email)
- [ ] Send 5-10 LinkedIn/beta personal DMs
- [ ] Send Resend blast to remaining 18 users

## Backend deploy
- [ ] Set SUNSET_MODE=true in Railway env vars for web service
- [ ] Verify upload returns 410: curl -X POST https://web-production-b3a4a.up.railway.app/api/v1/contacts/upload
- [ ] Verify intros returns 410: curl -X POST https://web-production-b3a4a.up.railway.app/api/v1/marketplace/intros

## Frontend deploy
- [ ] Set VITE_SUNSET_MODE=true in Railway env vars for frontend
- [ ] Trigger redeploy
- [ ] Verify banner visible at https://warmpath.majiq.agency

## Disable Clerk signups
- [ ] Clerk dashboard > Settings > Sign-up > disable new signups
- [ ] Verify sign-up page shows appropriate error

## Stop internal services (Gate 2)

Pre-check:
- [ ] Verify no in-flight uploads: query_sql("SELECT count(*) FROM csv_uploads WHERE status = 'processing'")
- [ ] Verify active user identity: query_sql("SELECT user_id FROM usage_logs WHERE created_at > NOW() - INTERVAL '7 days' GROUP BY user_id")

Stop services:
- [ ] Railway: Scale worker to 0 / remove
- [ ] Railway: Scale beat to 0 / remove
- [ ] Railway: Scale agent-runtime to 0 / remove
- [ ] Railway: Scale mcp-server to 0 / remove
- [ ] Disable all Railway Cron jobs
- [ ] Verify only web + frontend + Postgres + Redis remain

## Verification
- [ ] Visit https://warmpath.majiq.agency — banner visible
- [ ] Attempt upload — 410 returned
- [ ] Attempt intro request — 410 returned
- [ ] Attempt signup — blocked by Clerk
