# Contributing

> **Project status:** WarmPath was sunset on April 28, 2026.
> Pull requests and issues against this repository are **not actively
> reviewed or merged**. The code is preserved for reference and learning.

If you'd like to keep building on it, fork the repo and maintain your own
line. The notes below are for forks and self-maintainers.

## Local development

Prerequisites: Docker, GNU Make, Python 3.11+, Node 20+.

```bash
cp .env.dev.example .env.dev   # fill in API keys you actually need
make dev                       # Postgres + Redis + Qdrant + API + worker + frontend
make seed                      # populate dev DB with test data
make test                      # run pytest (smoke + full suites)
```

API: `http://localhost:8000` · Frontend: `http://localhost:5173`

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the high-level design and
[`frontend/README.md`](frontend/README.md) for frontend-specific setup.

## Updating dependencies

1. Edit `requirements.txt` (production) or `requirements-test.txt` (test-only additions).
2. Run `make lock` to regenerate `requirements-test.lock`. Requires `uv` — install with `pipx install uv` (or the upstream installer from <https://docs.astral.sh/uv/>) if missing.
3. Commit the `.txt` and the `.lock` together. CI's `lock-freshness` job will fail the PR otherwise.

The lock file is Linux-x86_64-pinned (`--python-platform linux --python-version 3.11`). `make lock` produces the same output on any dev machine. Local installs on macOS/Windows should use `pip install -r requirements-test.txt` (floor bounds) rather than the lock — the lock will refuse to install on other platforms.

## Tests and linting

```bash
pytest -m smoke -q             # fast critical-path tests (~5s)
pytest -n auto --timeout=120   # full suite (3,100+ tests)
ruff format . && ruff check .  # Python lint
cd frontend && npm run lint    # frontend lint
```

CI configuration lives in [`.github/workflows/ci.yml`](.github/workflows/ci.yml).
It still runs on pushes to forks if you keep Actions enabled.

## License and attribution

This project is licensed under [Apache-2.0](LICENSE). Any contribution
you make to a fork is assumed to be under the same license. See
[`NOTICE`](NOTICE) for attribution requirements.

## Conduct

Forks are expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md)
in their own communities; this repo's discussions/issues are closed.
