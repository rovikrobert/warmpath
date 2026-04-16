# Security Policy

## Project status

> **WarmPath was sunset on April 28, 2026.** This repository is archived
> and **no further security patches will be released** by the original
> author. Do not deploy this code as-is to production.

## Known posture at sunset

- Dependencies were last audited via `pip-audit` and the dep-audit CI
  job — see [`.github/workflows/ci.yml`](.github/workflows/ci.yml) for
  ignored advisories and rationale.
- The codebase has Python and TypeScript security scanners wired into
  CI (`scripts/security_scan.py`, ruff, eslint). Re-run them in your
  fork before deploying.
- Secrets are read from environment variables only — see
  [`.env.dev.example`](.env.dev.example) for the full surface.

## Reporting a vulnerability

This repo is no longer monitored, so there is no triage process here.

- **If you fork and run this code**, treat security issues as your own
  responsibility. Publish a `SECURITY.md` in your fork with a reporting
  channel you actually monitor.
- **If you discover a vulnerability that affects users of the original
  hosted WarmPath service** (which has been shut down), no action is
  required — the service no longer exists.

## License

Use of this code is governed by [Apache-2.0](LICENSE), which provides it
"AS IS" without warranty of any kind.
