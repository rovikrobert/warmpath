# CI speed and reproducibility — design

Date: 2026-04-16
Status: approved (pending user spec review)
Scope: `.github/workflows/*.yml`, `requirements*.txt`, new lock files, new composite action, Makefile targets. No application or Docker image changes in this pass.

## Goals

1. Cut CI wall-clock time on PRs that don't change dependencies by caching Python package installs.
2. Remove duplication across the 10 CI jobs where doing so doesn't degrade per-check failure signals.
3. Make Python dependency installs byte-for-byte reproducible across CI runs and local machines.

## Non-goals

- No changes to `Dockerfile` / `Dockerfile.dev` in this pass (separable follow-up; production image determinism has its own blast radius).
- No merging of jobs into matrices. Independent green/red, independent timeouts, and independent re-run buttons are load-bearing.
- No Python version bump, no tooling-migration to Poetry / Hatch / pip-tools. `uv` stays the CI installer.
- No frontend / `npm` changes. Node already has `cache: 'npm'` via `actions/setup-node@v4`.

## Current state (as of 2026-04-16)

- `.github/workflows/ci.yml` has 10 jobs, all `ubuntu-latest`, all `python-version: '3.11'`. None enable a Python dependency cache.
- Only two jobs install non-trivial Python deps: `test` (`uv pip install --system -r requirements-test.txt`) and `dep-audit` (`uv pip install --system pip-audit==2.9.0`). The `lint` job does `pip install ruff==0.15.1`.
- Six jobs are stdlib-only (`security-scan`, `privacy-scan`, `n-plus-one-check`, `async-lint`, `agent-config-check`, `telemetry-scan`). They run `actions/checkout` + `actions/setup-python@v5` then invoke a stdlib script.
- `.github/workflows/auto-lint.yml` does `pip install ruff` (unpinned, uncached).
- `.github/workflows/auto-deps.yml` does `pip install -r requirements.txt pip-audit` (uncached).
- `requirements.txt`, `requirements-test.txt`, `requirements-dev.txt` all use `>=` floors. No lock file of any kind.
- `requirements-dev.txt` is **not referenced by any CI job, Dockerfile, or Makefile target**. It lists `mypy` and `pytest-cov` which `requirements-test.txt` lacks — silent drift.
- `Dockerfile` and `Dockerfile.dev` install from `requirements.txt` (left unchanged in this pass).

## Design

### 1. Caching

**uv cache** on the two jobs that use uv:

```yaml
- uses: astral-sh/setup-uv@v4
  with:
    enable-cache: true
    cache-dependency-glob: |
      requirements*.txt
      requirements*.lock
```

Applied to `test` and `dep-audit`. `setup-uv` writes to `~/.cache/uv` and keys on the glob's hashed contents; no `actions/cache` boilerplate needed.

**pip cache** on the three jobs that use bare `pip`:

- `lint` job: add a new `requirements-lint.txt` containing `ruff==0.15.1`. Use `actions/setup-python@v5` with `cache: 'pip'` and `cache-dependency-path: requirements-lint.txt`.
- `auto-lint.yml`: **does not** adopt the pin, and **does not cache**. Its purpose is to surface new ruff rules automatically — pinning defeats that, and a stable pip-cache key would serve stale wheels (PyPI update → cache never invalidates unless the key changes). The job runs once daily; the ~3-5 s saved by caching isn't worth the staleness trap. A human bumping `requirements-lint.txt` is the mechanism that promotes new rules into the PR-blocking `lint` job.
- `auto-deps.yml`: `cache: 'pip'`, `cache-dependency-path: requirements.txt`.

The six stdlib-only jobs install nothing, so caching is a no-op for them; they are unchanged except for the composite action (next section).

### 2. Consolidation

**Composite action**: `.github/actions/setup-python-warmpath/action.yml` wraps `actions/setup-python@v5` pinned to `3.11`. It does **not** bundle `actions/checkout@v4` because a local composite action (`uses: ./…`) can only run after the repo is already checked out — chicken-and-egg. Each job still calls `actions/checkout@v4` as its first step; the composite is step two. Accepts two inputs:

- `cache` (default `''`) — passed through to setup-python's `cache:` input. Set to `'pip'` by jobs that want pip caching; left empty (no cache) by stdlib-only jobs.
- `cache-dependency-path` (default `''`) — passed through to setup-python's `cache-dependency-path:`. Required when `cache` is set.

setup-python only activates caching when both are truthy, so the default (both empty) is a no-op — safe for the six stdlib-only jobs. Every job's first step becomes `uses: ./.github/actions/setup-python-warmpath` (plus inputs where applicable). A future Python bump is a single-line edit inside the composite instead of 10 edits across `ci.yml`.

**What I am not doing**:

- Not collapsing stdlib-only scanners into a matrix job. The brief explicitly protects failure-signal quality, and named jobs with independent status checks are more useful to maintainers and branch-protection rules than a single striped "Scanners" check.
- Not merging `test` and `lint`. Different timeouts (15 vs 5 min) and different dependency surfaces.

**Cleanup**: delete `requirements-dev.txt`. It is unused, drifted from `requirements-test.txt`, and keeping it creates a trap for new contributors. The two deps it uniquely provides (`mypy`, `pytest-cov`) are not invoked by any CI job or Makefile target; anyone who wants them locally can install them ad-hoc or add them to `requirements-test.txt` in a follow-up.

### 3. Deterministic dependency strategy — `uv pip compile`

Adopt a compiled lock file produced by `uv pip compile --generate-hashes`. `requirements.txt` and `requirements-test.txt` remain the **human-editable source of truth** (loose floor bounds, comments, security annotations). One new file, committed:

- `requirements-test.lock` — compiled from `requirements-test.txt` (includes everything from `requirements.txt` via its `-r` directive, so the test lock is a strict superset of the production set).

**Only one lock file this pass.** We considered also generating `requirements.lock` (production subset). Rejected because: (a) `Dockerfile` / `Dockerfile.dev` are out of scope this pass and are currently the only consumer that would want a prod-only lock; (b) `dep-audit` can audit `requirements-test.lock` and still catch every production vulnerability — the extra test deps add noise but not false negatives; (c) maintaining two locks risks their shared-dep versions diverging if PyPI releases between generations. Revisit when Dockerfile switches to the lock.

CI installs from `requirements-test.lock`; maintainers edit `requirements.txt` or `requirements-test.txt` and run `make lock` to regenerate. Hashes in the lock file make installs tamper-evident (`uv pip install` verifies SHA-256 of every wheel/sdist).

**Platform pinning (critical)**: `uv pip compile --generate-hashes` defaults to the host platform, so a macOS-arm64 dev and an ubuntu-latest-x86_64 CI runner would produce lock files with different wheel hashes for the same dependency set, causing the freshness check to fail for reasons unrelated to dep changes. The compile command is pinned to CI's target:

```
uv pip compile \
  --generate-hashes \
  --no-header \
  --python-platform linux \
  --python-version 3.11 \
  requirements-test.txt \
  -o requirements-test.lock
```

Consequence: the lock file is Linux-specific. Local macOS/Windows devs should `pip install -r requirements-test.txt` (floor bounds) for local dev, or use Docker to run the lock. This is documented in migration notes. If cross-platform CI is added later, switch to `--universal`.

**Freshness enforcement**: new CI job `lock-freshness` re-runs the exact compile command (same `--python-platform`, `--python-version`, `--no-header` flags) against the current `requirements-test.txt` into a temp location and diffs against the committed `requirements-test.lock`. Fails the build if they disagree. This catches maintainers who edit a `.txt` file without regenerating the lock.

The Makefile target and the CI freshness job **must invoke uv with identical flags**. To enforce this, `make lock` and `make lock-check` share a single variable (e.g. `UV_COMPILE_FLAGS`) defined in the Makefile, and the CI job calls `make lock-check` rather than re-spelling the command. `--no-header` is required to suppress the command-invocation comment uv otherwise writes into the lock header, which would cause spurious diffs.

**Makefile targets**:

- `make lock` — regenerate `requirements-test.lock`.
- `make lock-check` — same check as the CI job, for local pre-push verification.

**`dep-audit` update**: switch from `pip-audit -r requirements.txt` to `pip-audit -r requirements-test.lock`. This audits what CI actually installs (exact pinned versions + hashes), not what PyPI's current resolution of floor bounds would produce. Existing `--ignore-vuln` flags carry over unchanged.

**`auto-deps.yml` update** — sequencing matters, and the design fails closed:

1. `pip-audit --fix` (existing step) modifies the installed environment.
2. `pip freeze` → merge bumped versions back into `requirements.txt` (existing step, unchanged).
3. **New**: run `make lock` to regenerate `requirements-test.lock` against the updated `requirements.txt`.
4. **New fail-closed**: if step 3 fails (network flake, unresolvable constraint, hash mismatch), the workflow **still opens the PR** but includes only the `requirements.txt` change and a warning in the PR body asking the maintainer to regenerate the lock manually. This keeps security fixes flowing even when the lock path breaks; the `lock-freshness` check on the PR will then block merge until resolved, which is the desired signal.
5. Commit includes both `requirements.txt` and `requirements-test.lock` (or just the former, with the warning).

**Why `uv pip compile` over alternatives**:

- `uv.lock` (uv's native lockfile) requires migrating to PEP 621 `[project]` metadata in `pyproject.toml` and switching the dev loop to `uv sync`. Larger blast radius, touches `Dockerfile` assumptions, changes what new contributors type. Rejected for this pass.
- `constraints.txt` (installed with `-c`) is functionally close to a lock but requires two files (`requirements.txt` + `constraints.txt`) with overlapping roles; `uv pip compile`'s output *is* a constraints-style file with hashes, produced from one canonical input. Simpler.

## File-by-file changes

| File | Action |
|---|---|
| `.github/actions/setup-python-warmpath/action.yml` | **New**. Composite: checkout + setup-python@v5 (3.11). Two optional inputs: `cache`, `cache-dependency-path` (both pass-through to setup-python). |
| `.github/workflows/ci.yml` | Replace 10× checkout/setup-python pairs with composite. Add uv cache to `test` and `dep-audit`. Swap `test` install to `requirements-test.lock`. Swap `dep-audit` to `pip-audit -r requirements-test.lock`. Add new `lock-freshness` job. |
| `.github/workflows/auto-lint.yml` | Use composite. Keep `pip install ruff` unpinned (latest). No pip cache (stable key would serve stale wheels; daily job, not worth it). |
| `.github/workflows/auto-deps.yml` | Use composite with `cache-dependency-path: requirements.txt`. After `pip-audit --fix` + `requirements.txt` merge, run `make lock`; on lock-regen failure, open PR without lock update + warning in body. |
| `requirements-lint.txt` | **New**. One line: `ruff==0.15.1`. Used by the PR-blocking `lint` job only. |
| `requirements-test.lock` | **New**. Generated by `uv pip compile --generate-hashes --no-header --python-platform linux --python-version 3.11 requirements-test.txt -o requirements-test.lock`. |
| `requirements-dev.txt` | **Deleted**. Unused and drifted. |
| `Makefile` | Add `lock` and `lock-check` targets. |
| `CONTRIBUTING.md` | Add a short "Updating dependencies" section pointing at `make lock`. |
| `Dockerfile`, `Dockerfile.dev` | **Unchanged** this pass. Follow-up ticket. |

## Expected savings and trade-offs

Rough numbers based on the dependency set (`langchain-*`, `langgraph-*`, `pandas`, `sqlalchemy`, `openai`, `anthropic`, `qdrant-client`, `sentry-sdk`, etc. — the test set is wide):

- Cold install (cache miss, first run on a new branch or after a dep change): **~60–90 s** for `test`, **~5 s** for `dep-audit`, **~3 s** for `lint`. Unchanged by this work.
- Warm install (cache hit, deps unchanged): **~5–15 s** for `test`, **~1–2 s** for `dep-audit`, **~1 s** for `lint`.
- Net PR savings when deps are unchanged: **~45–75 s** per run, concentrated in `test`. This is the common case.
- `lock-freshness` adds ~5–10 s (fresh uv cache + one `uv pip compile`). Strictly smaller than the savings it enables.

**Trade-offs**:

- Lock files add commit churn when deps change. Mitigated by `make lock` being one command and the freshness check catching forgotten regenerations before merge.
- Composite action adds one layer of indirection when reading workflow YAML. Mitigated by the composite being 15 lines and doing exactly one thing.
- Generated hashes slow `uv pip compile` itself (hash every wheel/sdist). Measured: ~10–20 s one-time; acceptable for determinism gains.
- Deleting `requirements-dev.txt` may surprise a contributor who was using it locally. Mitigated by migration notes and because nothing in repo tooling exercised it.
- First run on each branch still pays the cache-miss cost. No way around that without a self-hosted runner or GitHub Enterprise cache; out of scope.
- Savings estimates are unverified engineering guesses; first real CI run after merge will measure and should inform whether further optimization is worth pursuing.
- Lock file is Linux-x86_64-pinned. macOS/Windows devs cannot install from it directly; they install from `requirements-test.txt`. Acceptable because local dev already tolerates floor-bound resolution, and CI is the reproducibility-critical surface.

## Known follow-ups (out of scope this pass)

- **Dockerfile / Dockerfile.dev** should install from `requirements-test.lock` (or a prod-only lock if/when we add one) for production-image reproducibility. Separate PR; touches production build.
- **Stdlib-only scanner drift**: six scanner jobs assume their scripts import nothing outside the Python stdlib. Nothing enforces this. A future edit adding `import requests` would silently fail at runtime. A small AST-based check (or a `grep -E '^(from|import) ' | grep -v stdlib-allowlist`) belongs in a follow-up PR.
- **Cross-platform lock** via `--universal` if macOS or Windows CI runners are ever added.
- **Branch protection**: maintainers may want to make `lock-freshness` a required status check. Not enforced here — a design recommendation only.

## Migration notes (for maintainers and forks)

1. **Updating a dependency**: edit `requirements.txt` or `requirements-test.txt` as before, then run `make lock` and commit the regenerated `requirements-test.lock` alongside the `.txt` change. CI's `lock-freshness` job will fail the PR otherwise.
2. **Local install from lock (Linux only)**: `uv pip install -r requirements-test.lock`. On macOS/Windows this will fail because the lock is Linux-x86_64-pinned; use `uv pip install -r requirements-test.txt` for local dev, or run inside Docker if you need an exact CI repro.
3. **`uv` not installed locally**: `pip install uv` (or `pipx install uv`) — the Makefile target calls `uv` from `$PATH`.
4. **Mypy / pytest-cov users**: `requirements-dev.txt` is removed in this pass (it was unused by CI and had drifted from `requirements-test.txt`). Install ad-hoc with `uv pip install mypy pytest-cov`, or open a follow-up PR to add them to `requirements-test.txt` and relock.
5. **Auto-deps PRs**: now include `requirements.txt` diffs *and usually* a `requirements-test.lock` diff. If the PR body contains a "lock regeneration failed" warning, regenerate the lock locally (`make lock`) and push before merging — `lock-freshness` will block merge until resolved.
6. **Branch protection**: maintainers may want to promote `lock-freshness` to a required status check. Recommended but not enforced here.

## Verification

Before declaring complete:

1. `actionlint .github/workflows/*.yml` (or GitHub's web-based linter via `gh workflow view`) passes.
2. A dry-run PR against a fork triggers the workflow; all 10 existing job names still appear in the checks UI plus the new `lock-freshness`.
3. `make lock-check` exits 0 on a freshly-cloned checkout.
4. Deliberately flip one version in `requirements.txt`, push — `lock-freshness` fails with a clear diff; `make lock` locally regenerates and the diff disappears on re-push.
5. Cache-hit path observed on a second run: the "Install dependencies" step reports a cache restore (check action logs for "cache hit" from `setup-uv` / `setup-python`).
6. `pip-audit -r requirements-test.lock` runs cleanly against the committed lock with the existing `--ignore-vuln` allowlist.
7. Run `make lock` on macOS — output matches what CI produces (because of `--python-platform linux`). Spot-check one wheel hash against the CI-produced version.
