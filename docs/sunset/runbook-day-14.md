# Day 14 Runbook (2026-04-28)

## Pre-flight (Gate 3)
- [ ] All export requests fulfilled (grep inbox for "warmpath" + "export")
- [ ] Zero open export tickets

## Database snapshot

```bash
# Step 1: Dump
PATH="/opt/homebrew/opt/libpq/bin:$PATH" \
  pg_dump --format=custom --compress=9 \
  "$DATABASE_URL" \
  > warmpath_final_2026-04-28.dump

# Step 2: Verify non-empty
ls -la warmpath_final_2026-04-28.dump

# Step 3: Encrypt
gpg --symmetric --cipher-algo AES256 \
  --output warmpath_final_2026-04-28.dump.gpg \
  warmpath_final_2026-04-28.dump

# Step 4: Verify round-trip
gpg --decrypt warmpath_final_2026-04-28.dump.gpg > /tmp/roundtrip_test.dump
diff warmpath_final_2026-04-28.dump /tmp/roundtrip_test.dump
rm /tmp/roundtrip_test.dump

# Step 5: Shred unencrypted dump
shred -u warmpath_final_2026-04-28.dump

# Step 6: Upload .dump.gpg to 1Password vault "WarmPath Sunset Archive"
```

## Git bundle (existing private repo)

```bash
git bundle create warmpath-final.bundle --all
gpg --symmetric --cipher-algo AES256 \
  --output warmpath-final.bundle.gpg \
  warmpath-final.bundle
shred -u warmpath-final.bundle
# Upload warmpath-final.bundle.gpg to same 1Password vault
```

## Delete Railway services
- [ ] Delete Postgres plugin (AFTER snapshot is verified)
- [ ] Delete Redis plugin
- [ ] Delete web service
- [ ] Delete frontend service
- [ ] Delete any remaining stopped services
- [ ] Verify Railway project has no running services

## Set up redirect
- [ ] Create Cloudflare Pages or Vercel project for warmpath.majiq.agency
- [ ] Configure redirect: /* -> https://majiq.agency/warmpath (301)
- [ ] Update DNS: CNAME warmpath.majiq.agency to the pages/vercel domain
- [ ] Verify: curl -I https://warmpath.majiq.agency/anything returns 301

## PII cleanup
- [ ] Clerk: Delete all 27 users via dashboard
- [ ] Resend: Delete event logs via dashboard or API
- [ ] W&B Weave: Delete warmpath project
- [ ] Stripe: Delete all customer objects
- [ ] Telegram: Delete @WarmChatCoS_Bot via @BotFather + clear chat
- [ ] Qdrant: Delete warmpath_memory collection
- [ ] GitHub: Delete private warmpath repo (AFTER bundle verified)
- [ ] Local: rm -rf agents/*/reports/ .playwright-mcp/ .superpowers/ .serena/

## Verification (Gate 3 completion)
- [ ] Railway: no running services
- [ ] curl -I https://warmpath.majiq.agency returns 301
- [ ] Clerk: 0 users
- [ ] Resend: empty event log
- [ ] W&B: warmpath project gone
- [ ] Stripe: stripe customers list returns empty
- [ ] 1Password: both .gpg files visible
