# WarmPath Architecture Guide

Quick cross-reference for navigating the codebase. For full project context, see [CLAUDE.md](CLAUDE.md).

---

## Module Map

### Request Lifecycle

```
HTTP Request
  → Middleware (security_headers → usage tracking → rate_limit)
  → API route (app/api/*.py)
    → Dependency injection (get_current_user / requi[RESEND_KEY_REDACTED])
    → Service layer (app/services/*.py)
    → ORM models (app/models/*.py)
  → JSON response envelope: {data: ..., meta: {...}}
```

### API Routes → Services → Models

#### Auth (`app/api/auth.py`)
```
POST /signup     → email_service, credits.earn_credits(50)  → User, ConnectorProfile, CreditTransaction
POST /login      → audit_logger                             → User, AuditLog
POST /refresh    → audit_logger                             → User, AuditLog
POST /change-password → audit_logger                        → User, AuditLog  (increments token_version)
POST /logout-all → audit_logger                             → User, AuditLog  (increments token_version)
GET  /verify-email → email_service.verify_token             → User, AuditLog
```

#### Contacts (`app/api/contacts.py`)
```
POST /upload        → csv_parser, process_csv_upload_core   → CsvUpload, Contact  (+100 credits)
POST /compute-scores → warm_scorer.batch_compute_scores     → WarmScore
POST /manual        → csv_parser.generate_fingerprint,
                      company_normalizer.link_contact       → Contact, Company, WarmScore
```

#### Search (`app/api/search.py`)
```
POST /search/{id}/run → ai_matcher.run_search              → SearchRequest, MatchResult
POST /search/smart    → job_fetcher, ai_matcher,
                        warm_scorer, credits                → SearchRequest, UserJobPreferences,
                                                               Contact, MarketplaceListing
```

#### Marketplace (`app/api/marketplace.py`)
```
POST /search         → credits.spend_credits(5)             → MarketplaceListing, ConnectorReputation
POST /request-intro  → credits.spend_credits(20)            → IntroFacilitation, Contact
PATCH /requests/{id} → approve: credits.earn_credits(50)    → IntroFacilitation, ConnectorReputation
                       decline: credits.refund_credits(15)
PUT /sharing-prefs   → marketplace_indexer.generate_listings → NetworkSharingPreferences, MarketplaceListing
```

#### Applications (`app/api/applications.py`)
```
POST /from-intro/{id} → (prefills from IntroRequest)       → IntroRequest, Contact, Application
PATCH /{id}           → (auto-sets sent_at, responded_at)   → Application
```

---

## Data Flow Diagrams

### CSV Upload → Marketplace
```
User uploads CSV
  → csv_parser.parse_linkedin_csv()         # normalize, sanitize, fingerprint
  → suppression.check_suppression()          # skip suppressed contacts
  → company_normalizer.normalize_name()      # strip suffixes, match aliases
  → company_normalizer.link_contact()        # create/find Company, link via ContactCompany
  → credits.earn_credits(user, 100)          # award upload credits
  → warm_scorer.batch_compute_scores()       # compute warm scores

Network holder opts into marketplace:
  → marketplace_indexer.generate_listings()   # create anonymized MarketplaceListings
     - Only contacts with company_id
     - Checks suppression list, exclusions, category filters
     - Classifies: role_level, department_category, warm_sco[RESEND_KEY_REDACTED], connection_recency
     - No PII crosses the vault boundary
```

### Marketplace Intro Flow
```
Job seeker searches marketplace (POST /marketplace/search)
  → Anonymized results: {listing_id, company_name, role_level, department_category}
  → Costs 5 credits

Job seeker requests intro (POST /marketplace/request-intro)
  → Duplicate check (SHA-256 hash: does seeker already have this contact?)
  → Costs 20 credits
  → Creates IntroFacilitation (status: requested)

Network holder reviews (GET /marketplace/incoming-requests)
  → Sees their OWN contact's PII + job seeker's profile snapshot
  → Approves → holder earns 50 credits, seeker sees status update
  → Declines → seeker gets 15 credit refund

IMPORTANT: Seeker NEVER sees contact PII, even after approval.
Identity flows through the network holder's active choice (they send the intro).
```

### Smart Search
```
POST /search/smart {company_names: [...], scope: "own_network" | "marketplace"}
  1. Requires job preferences (target_role) set via PUT /preferences/job
  2. For each company:
     a. Fetch job openings (Greenhouse API → Lever API → career page scraper → skip)
     b. Score own-network contacts against target role
     c. If scope=marketplace: search anonymized listings (costs 5 credits)
  3. Return companies grouped with active_openings + referral_paths
```

---

## Security Gates

| Dependency | Applied To | Effect |
|------------|-----------|--------|
| `get_current_user` | Most endpoints | Validates JWT, returns User |
| `requi[RESEND_KEY_REDACTED]` | Marketplace search, request-intro, credit purchase | 403 if `email_verified=False` |
| `check_rate_limit` | CSV upload, search run | Counts UsageLog rows, 429 if exceeded |

### Token Versioning
- `token_version` (int) on User model, embedded in every JWT
- Incremented on: password change, logout-all
- Mismatch = 401 Unauthorized (all old tokens invalidated)

### Account Lockout
- 5 failed logins → `locked_until` set to now + 15 minutes → 429
- Reset on successful login

---

## Credit Economy

| Action | Credits | Direction |
|--------|---------|-----------|
| Welcome bonus (signup) | +50 | earned |
| CSV upload | +100 | earned |
| Facilitate intro (approve) | +50 | earned |
| Marketplace search | -5 | spent |
| Request intro | -20 | spent |
| Declined intro (refund to seeker) | +15 | refund |
| Direct purchase | configurable | purchased |

Balance = `SUM(amount)` from `credit_transactions`. Non-transferable. 12-month expiry.

---

## Testing

### Setup
- **Engine**: SQLite in-memory (`sqlite+aiosqlite://`)
- **Type patches**: JSONB→JSON, INET→VARCHAR(45), ARRAY→JSON, UUID→CHAR(36)
- **Env**: `AI_MOCK_MODE=true`, `CSV_ASYNC_PROCESSING=false`
- **Fixtures**: `client` (AsyncClient), `truncate_tables` (auto-cleans between tests)

### Direct DB Access
```python
from tests.conftest import TestSessionLocal
from sqlalchemy import select

async with TestSessionLocal() as session:
    result = await session.execute(select(Model).where(...))
```

### Test File Map
| File | What It Tests |
|------|--------------|
| `test_auth.py` | Signup, login, refresh, verify, lockout |
| `test_csv_parser.py` | CSV parsing, fingerprinting, sanitization |
| `test_warm_scorer.py` | Warm score computation, referral_likelihood |
| `test_search.py` | Search CRUD, AI matching, results |
| `test_intro_drafter.py` | Multi-step culturally-aware messages |
| `test_applications.py` | App CRUD, pipeline, stats, from-intro |
| `test_marketplace.py` | Indexing, classification, anonymization |
| `test_marketplace_api.py` | Marketplace API: search, intros, credits, sharing |
| `test_credits.py` | Earn, spend, refund, expiry |
| `test_privacy.py` | Suppression list, deletion cascades |
| `test_usage_metering.py` | Metered logging, usage API, tier warnings |
| `test_relationship_manual.py` | Relationship types, work history, manual contacts |
| `test_sea_boards.py` | SEA/India/ANZ registry, career page scraper |
| `test_security.py` | JWT refresh, CSV limits, headers, lockout, webhooks |
| `test_integration.py` | End-to-end solo + marketplace + privacy compliance |
| `test_smart_search.py` | Smart search, job preferences |
| `test_usage_and_errors.py` | Usage tracking, error handlers |
| `test_company_normalizer.py` | Company name normalization |
| `test_job_fetcher.py` | Greenhouse/Lever/career page fetching |

### Application Status Values
```
draft → message_sent → responded → interview_scheduled → interviewed → offer_received → offer_accepted
Also: rejected, withdrawn, no_response
```

---

## Key Conventions

- **Response envelope**: `{"data": ..., "meta": {...}}` on all endpoints
- **IDs**: UUID everywhere (never auto-increment)
- **Soft delete**: `deleted_at` column (except `audit_logs` — append-only)
- **Timestamps**: UTC, `TIMESTAMP WITH TIME ZONE`
- **PII hashing**: `SHA-256(normalized_input)` — lowercase, trimmed
- **Marketplace boundary**: No names/emails cross the vault boundary without consent gate
