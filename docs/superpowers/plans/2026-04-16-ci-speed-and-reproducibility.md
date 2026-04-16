# CI Speed and Reproducibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Python dependency caching, consolidate repeated setup via a composite action, and introduce a `uv pip compile` lock + freshness check so CI installs are deterministic.

**Architecture:** One local composite action wraps `actions/setup-python@v5` (pinned to 3.11) with optional pass-through cache inputs. A single hash-pinned lock file (`requirements-test.lock`) produced by `uv pip compile --generate-hashes --python-platform linux --python-version 3.11` is the install source for CI and the audit target for `pip-audit`. A new `lock-freshness` job recompiles and diffs on every PR; a Makefile target (`make lock` / `make lock-check`) shares flags with CI. Spec: `docs/superpowers/specs/2026-04-16-ci-speed-and-reproducibility-design.md`.

**Tech Stack:** GitHub Actions, `astral-sh/setup-uv@v4`, `actions/setup-python@v5`, `uv pip compile`, `pip-audit`, GNU Make.

**Working directory:** `/Users/rovikrobert/code/warmpath-oss/warmpath`. All paths below are relative to it.

**Pre-flight:** Install `uv` locally (`pip install uv` or `pipx install uv`). Install `actionlint` if available (`brew install actionlint`); if not, each verification step falls back to `python -c "import yaml; yaml.safe_load(...)"`.

---

### Task 1: Add composite action `.github/actions/setup-python-warmpath`

**Files:**
- Create: `.github/actions/setup-python-warmpath/action.yml`

- [ ] **Step 1: Create the composite action file**

Create `.github/actions/setup-python-warmpath/action.yml`:

```yaml
name: Setup Python (warmpath)
description: Python 3.11 with optional pip cache, pinned for warmpath CI consistency.
inputs:
  cache:
    description: Pass-through to setup-python `cache` input (e.g. "pip"). Leave empty to disable caching.
    required: false
    default: ""
  cache-dependency-path:
    description: Pass-through to setup-python `cache-dependency-path`. Required when `cache` is set.
    required: false
    default: ""
runs:
  using: composite
  steps:
    - uses: actions/setup-python@v5
      with:
        python-version: "3.11"
        cache: ${{ inputs.cache }}
        cache-dependency-path: ${{ inputs.cache-dependency-path }}
```

Note: the composite does **not** include `actions/checkout@v4`. A local composite (`uses: ./…`) can only run after checkout has already populated the workspace, so each job still calls checkout as step 1.

- [ ] **Step 2: Validate YAML syntax**

Run: `python -c "import yaml, sys; yaml.safe_load(open('.github/actions/setup-python-warmpath/action.yml')); print('ok')"`

Expected: `ok`

If `actionlint` is available, also run: `actionlint -shellcheck= .github/actions/setup-python-warmpath/action.yml`
Expected: no output (exit 0).

- [ ] **Step 3: Commit**

```bash
git add .github/actions/setup-python-warmpath/action.yml
git commit -m "ci: add setup-python-warmpath composite action

Pins Python 3.11 and pipes cache inputs to setup-python@v5. Jobs
still call actions/checkout@v4 as step 1; the composite is step 2.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Wire the composite into every job in `ci.yml`

**Files:**
- Modify: `.github/workflows/ci.yml` (all 10 jobs)

Pure refactor — functional behavior unchanged. Each job's `actions/setup-python@v5` block is replaced with the composite.

- [ ] **Step 1: Read current `ci.yml`**

Run: `cat .github/workflows/ci.yml | head -40`
Expected: see the existing `test` job starting at line 15 with `actions/checkout@v4` then `actions/setup-python@v5` with `python-version: '3.11'`.

- [ ] **Step 2: Replace every `actions/setup-python@v5` block with the composite**

For **each** of the 10 jobs in `.github/workflows/ci.yml`, replace the block:

```yaml
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
```

with:

```yaml
      - uses: ./.github/actions/setup-python-warmpath
```

Keep the preceding `- uses: actions/checkout@v4` unchanged. Keep any `astral-sh/setup-uv@v4` step that follows.

Jobs to edit: `test`, `lint`, `frontend-build` (skip — uses Node), `security-scan`, `privacy-scan`, `n-plus-one-check`, `dep-audit`, `async-lint`, `agent-config-check`, `telemetry-scan`. **9 replacements total** (frontend-build uses `actions/setup-node@v4`, not setup-python — leave it alone).

- [ ] **Step 3: Validate YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('ok')"`
Expected: `ok`.

If `actionlint` is available: `actionlint .github/workflows/ci.yml`
Expected: exit 0.

- [ ] **Step 4: Verify all 9 replacements landed**

Run: `grep -c "setup-python-warmpath" .github/workflows/ci.yml`
Expected: `9`

Run: `grep -c "actions/setup-python@v5" .github/workflows/ci.yml`
Expected: `0`

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: wire setup-python-warmpath composite into all 9 Python jobs

Pure refactor — no functional change. Python version pin now lives
in one place instead of being duplicated across jobs.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Introduce `requirements-lint.txt` and switch the `lint` job to use it (with pip cache)

**Files:**
- Create: `requirements-lint.txt`
- Modify: `.github/workflows/ci.yml` (lint job)

- [ ] **Step 1: Create `requirements-lint.txt`**

Create `requirements-lint.txt` with exactly:

```
ruff==0.15.1
```

(The pin already present in `ci.yml`; we're relocating it.)

- [ ] **Step 2: Update the `lint` job in `.github/workflows/ci.yml`**

In the `lint` job, replace:

```yaml
      - uses: actions/checkout@v4

      - uses: ./.github/actions/setup-python-warmpath

      - name: Install ruff
        run: pip install ruff==0.15.1
```

with:

```yaml
      - uses: actions/checkout@v4

      - uses: ./.github/actions/setup-python-warmpath
        with:
          cache: pip
          cache-dependency-path: requirements-lint.txt

      - name: Install ruff
        run: pip install -r requirements-lint.txt
```

- [ ] **Step 3: Validate YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Verify no version drift**

Run: `grep ruff requirements-lint.txt`
Expected: `ruff==0.15.1`

Run: `grep ruff== .github/workflows/ci.yml`
Expected: no output (the pin has moved out of the workflow).

- [ ] **Step 5: Commit**

```bash
git add requirements-lint.txt .github/workflows/ci.yml
git commit -m "ci: pin ruff via requirements-lint.txt with pip cache

Extracts the hard-coded ruff==0.15.1 pin out of ci.yml so future
bumps are a one-file edit and pip caches it keyed on the file hash.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Enable uv cache on `test` and `dep-audit`

**Files:**
- Modify: `.github/workflows/ci.yml` (test job, dep-audit job)

- [ ] **Step 1: Update the `test` job's uv setup**

In the `test` job, find:

```yaml
      - uses: astral-sh/setup-uv@v4
```

Replace with:

```yaml
      - uses: astral-sh/setup-uv@v4
        with:
          enable-cache: true
          cache-dependency-glob: |
            requirements*.txt
            requirements*.lock
```

- [ ] **Step 2: Update the `dep-audit` job's uv setup**

Same replacement in the `dep-audit` job.

- [ ] **Step 3: Validate YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Verify both jobs got the cache block**

Run: `grep -c "enable-cache: true" .github/workflows/ci.yml`
Expected: `2`

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: enable uv cache on test and dep-audit jobs

Keyed on requirements*.txt and requirements*.lock. First run per
branch is unchanged; warm runs skip the install.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Generate `requirements-test.lock` and add Makefile targets

**Files:**
- Create: `requirements-test.lock`
- Modify: `Makefile`

- [ ] **Step 1: Add Makefile targets**

Open `Makefile`. Add to the **top** of the file (after any existing header comments, before the first target):

```makefile
UV_COMPILE_FLAGS := --generate-hashes --no-header --python-platform linux --python-version 3.11
```

Add these two targets (at the end of the file, or grouped with related targets — follow the file's existing convention):

```makefile
.PHONY: lock lock-check

lock: ## Regenerate requirements-test.lock from requirements-test.txt
	uv pip compile $(UV_COMPILE_FLAGS) requirements-test.txt -o requirements-test.lock

lock-check: ## Verify requirements-test.lock is fresh (used by CI)
	@tmp=$$(mktemp) && \
	uv pip compile $(UV_COMPILE_FLAGS) requirements-test.txt -o "$$tmp" >/dev/null && \
	if ! diff -u requirements-test.lock "$$tmp"; then \
	  echo ""; \
	  echo "ERROR: requirements-test.lock is out of date. Run 'make lock' and commit the result."; \
	  rm -f "$$tmp"; \
	  exit 1; \
	fi && \
	rm -f "$$tmp" && \
	echo "requirements-test.lock is up to date."
```

If `.PHONY:` is declared elsewhere in the Makefile, append `lock lock-check` to it instead of creating a new line.

- [ ] **Step 2: Run `make lock` to generate the lock file**

Run: `make lock`
Expected: `uv pip compile …` runs for 10-30 s (hashing every wheel). File `requirements-test.lock` is created in the repo root. No stderr errors. Exit 0.

If you see `uv: command not found`, install uv first: `pip install uv`. Then re-run.

- [ ] **Step 3: Sanity-check the generated lock**

Run: `head -5 requirements-test.lock`
Expected: no `# This file was autogenerated by uv via the following command:` header (because of `--no-header`). First lines should be package names with `==` pins and `--hash=sha256:...` entries.

Run: `grep -c -- '--hash=sha256:' requirements-test.lock`
Expected: a large number (>100). Every dep has ≥1 hash.

Run: `grep -c "^[a-zA-Z]" requirements-test.lock`
Expected: dozens (one line per package). All packages should appear with `==` pins — no `>=` floors in the lock.

- [ ] **Step 4: Verify `make lock-check` passes**

Run: `make lock-check`
Expected: `requirements-test.lock is up to date.` Exit 0.

- [ ] **Step 5: Deliberately break and re-verify**

Run: `echo "# tamper" >> requirements-test.lock && make lock-check`
Expected: diff printed + `ERROR: requirements-test.lock is out of date. Run 'make lock' and commit the result.` Exit 1.

Then restore: `make lock`

Run: `make lock-check`
Expected: `up to date.` Exit 0.

- [ ] **Step 6: Commit**

```bash
git add Makefile requirements-test.lock
git commit -m "build: add make lock targets and commit requirements-test.lock

uv pip compile with --generate-hashes --no-header --python-platform linux
--python-version 3.11. Lock pins every transitive dep + hashes for
tamper-evident installs. make lock-check powers the CI freshness gate.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Add the `lock-freshness` CI job

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Append the `lock-freshness` job**

At the end of the `jobs:` block in `.github/workflows/ci.yml`, add:

```yaml
  lock-freshness:
    name: Lock Freshness
    runs-on: ubuntu-latest
    timeout-minutes: 3
    steps:
      - uses: actions/checkout@v4

      - uses: ./.github/actions/setup-python-warmpath

      - uses: astral-sh/setup-uv@v4
        with:
          enable-cache: true
          cache-dependency-glob: |
            requirements*.txt
            requirements*.lock

      - name: Verify requirements-test.lock is fresh
        run: make lock-check
```

- [ ] **Step 2: Validate YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Confirm job is registered**

Run: `grep "lock-freshness:" .github/workflows/ci.yml`
Expected: one match.

Run: `grep -c "^  [a-z-]*:$" .github/workflows/ci.yml`
Expected: `11` (10 existing jobs + lock-freshness).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add lock-freshness job to block stale requirements-test.lock

Runs make lock-check on every PR. Fails if a maintainer edited a
requirements*.txt without regenerating the lock. Also catches
silent drift from upstream re-resolution.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Switch `test` job install to the lock file

**Files:**
- Modify: `.github/workflows/ci.yml` (test job)

- [ ] **Step 1: Update the install step**

In the `test` job, replace:

```yaml
      - name: Install dependencies
        run: uv pip install --system -r requirements-test.txt
```

with:

```yaml
      - name: Install dependencies
        run: uv pip install --system -r requirements-test.lock
```

- [ ] **Step 2: Validate YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Verify no other install site still points at `.txt`**

Run: `grep -n "requirements-test" .github/workflows/ci.yml`
Expected: every match references `requirements-test.lock` (except any `cache-dependency-glob` globs which match both).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: install test deps from requirements-test.lock

Hash-verified install. What CI installs is now byte-for-byte
reproducible from the committed lock.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Switch `dep-audit` to audit the lock

**Files:**
- Modify: `.github/workflows/ci.yml` (dep-audit job)

- [ ] **Step 1: Update the audit step**

In the `dep-audit` job, replace:

```yaml
      - name: Audit dependencies
        # GHSA-w8v5-vhqr-4h9v: diskcache pickle deserialization (transitive via weave).
        #   Local-only (CVSS 5.2), no fix version available. Revisit when diskcache >5.6.3 ships.
        # GHSA-7mpr-5m44-h73r: markdownify memory DoS via large HTML headlines.
        #   Unfixable: python-jobspy pins markdownify<0.14.0. Low risk — internal job scraping only.
        run: pip-audit -r requirements.txt --ignore-vuln GHSA-w8v5-vhqr-4h9v --ignore-vuln GHSA-7mpr-5m44-h73r
```

with:

```yaml
      - name: Audit dependencies
        # Audits the exact pinned versions CI installs (requirements-test.lock is a
        # superset of requirements.txt via its -r directive, so all prod deps are covered).
        # GHSA-w8v5-vhqr-4h9v: diskcache pickle deserialization (transitive via weave).
        #   Local-only (CVSS 5.2), no fix version available. Revisit when diskcache >5.6.3 ships.
        # GHSA-7mpr-5m44-h73r: markdownify memory DoS via large HTML headlines.
        #   Unfixable: python-jobspy pins markdownify<0.14.0. Low risk — internal job scraping only.
        run: pip-audit -r requirements-test.lock --ignore-vuln GHSA-w8v5-vhqr-4h9v --ignore-vuln GHSA-7mpr-5m44-h73r
```

- [ ] **Step 2: Validate YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Dry-run `pip-audit` locally to confirm the lock is audit-compatible**

Run: `pip install pip-audit==2.9.0` (if not already installed)

Run: `pip-audit -r requirements-test.lock --ignore-vuln GHSA-w8v5-vhqr-4h9v --ignore-vuln GHSA-7mpr-5m44-h73r`
Expected: exit 0 with `No known vulnerabilities found` (or equivalent). If new vulns appear here that weren't flagged before, they're real — surface them to the reviewer rather than silencing.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: audit requirements-test.lock instead of requirements.txt

Audits exact pinned versions that CI installs, not whatever PyPI's
current resolution of floor bounds would produce. Lock is a superset
of prod deps so no coverage is lost.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Update `auto-lint.yml` to use the composite (no cache)

**Files:**
- Modify: `.github/workflows/auto-lint.yml`

- [ ] **Step 1: Replace the setup-python block**

In `.github/workflows/auto-lint.yml`, replace:

```yaml
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
```

with:

```yaml
      - uses: ./.github/actions/setup-python-warmpath
```

Leave the `pip install ruff` step **unpinned** — the auto-lint workflow's purpose is to surface new ruff rules automatically. No pip cache (a stable cache key would serve stale wheels).

- [ ] **Step 2: Validate YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/auto-lint.yml')); print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Verify no unintended changes**

Run: `grep "pip install ruff" .github/workflows/auto-lint.yml`
Expected: `        run: pip install ruff` (unpinned, unchanged).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/auto-lint.yml
git commit -m "ci(auto-lint): use setup-python-warmpath composite

Ruff stays unpinned in this workflow — its purpose is to surface
new rules automatically. No cache for the same reason.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Update `auto-deps.yml` — composite, cache, lock regen with fail-closed

**Files:**
- Modify: `.github/workflows/auto-deps.yml`

This is the most involved workflow edit. The flow must: (1) use the composite with pip cache, (2) install `uv` alongside `pip-audit` (so `make lock` works), (3) regenerate the lock after `pip-audit --fix` + `requirements.txt` merge, (4) fail closed — if lock regen fails, still open a PR with the `.txt` change and a warning in the body.

- [ ] **Step 1: Replace the setup-python block with the composite (with pip cache)**

Replace:

```yaml
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
```

with:

```yaml
      - uses: ./.github/actions/setup-python-warmpath
        with:
          cache: pip
          cache-dependency-path: requirements.txt
```

- [ ] **Step 2: Install uv alongside pip-audit**

Replace:

```yaml
      - name: Install dependencies
        run: pip install -r requirements.txt pip-audit
```

with:

```yaml
      - name: Install dependencies
        run: pip install -r requirements.txt pip-audit uv
```

- [ ] **Step 3: Add lock regeneration with fail-closed after the freeze step**

Find the existing step:

```yaml
      - name: Freeze updated requirements
        if: steps.audit.outputs.has_vulns == 'true'
        run: |
          pip freeze > requirements.txt.new
          # ... (Python script that merges version bumps back into requirements.txt) ...
          rm -f requirements.txt.new
```

**Immediately after** that step (and **before** the `Check for changes` step), insert:

```yaml
      - name: Regenerate requirements-test.lock
        id: relock
        if: steps.audit.outputs.has_vulns == 'true'
        continue-on-error: true
        run: make lock

      - name: Record relock outcome
        if: steps.audit.outputs.has_vulns == 'true'
        id: relock_status
        run: |
          if [ "${{ steps.relock.outcome }}" = "success" ]; then
            echo "ok=true" >> "$GITHUB_OUTPUT"
          else
            echo "ok=false" >> "$GITHUB_OUTPUT"
          fi
```

- [ ] **Step 4: Update the PR creation step to stage the lock when fresh, and flag when not**

Find the existing `Create PR with security patches` step. Replace its `run:` block with:

```yaml
      - name: Create PR with security patches
        if: steps.changes.outputs.has_changes == 'true'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          BRANCH="auto/deps-security-$(date +%Y%m%d)"
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git checkout -b "$BRANCH"

          if [ "${{ steps.relock_status.outputs.ok }}" = "true" ]; then
            git add requirements.txt requirements-test.lock
            BODY="Automated dependency security fixes applied by \`pip-audit --fix\`. Lock file regenerated via \`make lock\`. Review changed package versions before merging."
          else
            git add requirements.txt
            BODY=$'Automated dependency security fixes applied by `pip-audit --fix`.\n\n**:warning: lock regeneration failed** — `requirements-test.lock` was NOT updated. The `lock-freshness` job on this PR will block merge. To resolve:\n\n```\nmake lock\ngit add requirements-test.lock\ngit commit --amend --no-edit\ngit push --force-with-lease\n```\n\nReview changed package versions before merging.'
          fi

          git commit -m "chore(deps): auto-fix security vulnerabilities

          Automated weekly dependency security scan via pip-audit.

          Co-Authored-By: github-actions[bot] <github-actions[bot]@users.noreply.github.com>"
          git push origin "$BRANCH"
          gh pr create \
            --title "chore(deps): security patches $(date +%Y-%m-%d)" \
            --body "$BODY" \
            --label "automated,security"
```

- [ ] **Step 5: Validate YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/auto-deps.yml')); print('ok')"`
Expected: `ok`.

If `actionlint` is available: `actionlint .github/workflows/auto-deps.yml`
Expected: exit 0.

- [ ] **Step 6: Sanity-check conditional branches**

Run: `grep -c "steps.relock_status.outputs.ok" .github/workflows/auto-deps.yml`
Expected: `1` (the conditional in the PR creation step).

Run: `grep -c "continue-on-error: true" .github/workflows/auto-deps.yml`
Expected: `1` (only the relock step).

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/auto-deps.yml
git commit -m "ci(auto-deps): regenerate lock after security fixes (fail-closed)

After pip-audit --fix + requirements.txt merge, run make lock.
If lock regen fails, still open the PR with a warning in the body —
lock-freshness will block merge until a maintainer regenerates.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: Remove `requirements-dev.txt` and document lock workflow

**Files:**
- Delete: `requirements-dev.txt`
- Modify: `CONTRIBUTING.md`

- [ ] **Step 1: Confirm nothing in the repo references `requirements-dev.txt`**

Run: `grep -rn "requirements-dev" --include="*.yml" --include="*.yaml" --include="*.txt" --include="Dockerfile*" --include="Makefile" --include="*.md" --include="*.py" --include="*.sh" .`

Expected: **zero matches** (or only matches in the file itself or this plan). If any workflow/script references it, stop and report — deletion is unsafe.

- [ ] **Step 2: Delete the file**

Run: `git rm requirements-dev.txt`
Expected: `rm 'requirements-dev.txt'`

- [ ] **Step 3: Add dependency-update docs to `CONTRIBUTING.md`**

Open `CONTRIBUTING.md`. Add a new section near the top (after the intro, before existing detailed sections):

```markdown
## Updating dependencies

1. Edit `requirements.txt` (production) or `requirements-test.txt` (test-only additions).
2. Run `make lock` to regenerate `requirements-test.lock`. Requires `uv` — install with `pip install uv` if missing.
3. Commit the `.txt` and the `.lock` together. CI's `lock-freshness` job will fail the PR otherwise.

The lock file is Linux-x86_64-pinned (`--python-platform linux --python-version 3.11`). `make lock` produces the same output on any dev machine. Local installs on macOS/Windows should use `pip install -r requirements-test.txt` (floor bounds) rather than the lock — the lock will refuse to install on other platforms.
```

- [ ] **Step 4: Validate `CONTRIBUTING.md` renders as valid Markdown**

Run: `python -c "import pathlib; print(pathlib.Path('CONTRIBUTING.md').read_text().count('## '))"`
Expected: a positive integer ≥ 2 (at least the new section + existing section).

- [ ] **Step 5: Commit**

```bash
git add CONTRIBUTING.md
git commit -m "chore: drop requirements-dev.txt, document make lock workflow

requirements-dev.txt was unused by CI and had drifted from
requirements-test.txt. CONTRIBUTING now describes the lock workflow
and documents the Linux-pinned lock caveat for macOS/Windows devs.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: End-to-end verification

**Files:** none (read-only checks).

- [ ] **Step 1: Full YAML syntax check on every workflow**

Run: `python -c "import yaml,glob; [yaml.safe_load(open(p)) for p in glob.glob('.github/workflows/*.yml')]; print('all ok')"`
Expected: `all ok`.

- [ ] **Step 2: Actionlint sweep (if installed)**

Run: `actionlint .github/workflows/*.yml` (skip if `actionlint` is not installed).
Expected: exit 0, no output.

- [ ] **Step 3: Lock freshness holds**

Run: `make lock-check`
Expected: `requirements-test.lock is up to date.`

- [ ] **Step 4: Job-count sanity check**

Run: `grep -c "^  [a-z-]*:$" .github/workflows/ci.yml`
Expected: `11` (10 original + `lock-freshness`).

Run: `grep "name:" .github/workflows/ci.yml | grep -v "cache-dependency" | head -20`
Expected: lists all 11 jobs by human-readable name; none are renamed from the original set.

- [ ] **Step 5: Composite action is referenced exactly where expected**

Run: `grep -c "setup-python-warmpath" .github/workflows/ci.yml`
Expected: `10` (9 original Python jobs + new `lock-freshness`).

Run: `grep -c "setup-python-warmpath" .github/workflows/auto-lint.yml`
Expected: `1`.

Run: `grep -c "setup-python-warmpath" .github/workflows/auto-deps.yml`
Expected: `1`.

- [ ] **Step 6: No stale references**

Run: `grep -rn "requirements-dev" .github/ Makefile Dockerfile Dockerfile.dev docker-compose.dev.yml CONTRIBUTING.md README.md 2>/dev/null`
Expected: no output.

Run: `grep -rn "requirements.txt" .github/workflows/ci.yml`
Expected: matches only in the `cache-dependency-glob` block and any comments — no `pip install -r requirements.txt` calls.

- [ ] **Step 7: Deliberate break-and-restore rehearsal**

Run: `sed -i.bak 's/fastapi>=0.135.1/fastapi>=0.200.0/' requirements.txt`

Run: `make lock-check`
Expected: diff output + `ERROR: requirements-test.lock is out of date` + exit 1.

Restore: `mv requirements.txt.bak requirements.txt`

Run: `make lock-check`
Expected: `up to date.` Exit 0.

- [ ] **Step 8: Summarize what will happen on the next CI run**

Write a short summary (for the PR description or your review notes):

- All 11 jobs still present; no renames → branch protection unaffected.
- `test` and `dep-audit` now cache via `setup-uv` + install from `requirements-test.lock`.
- `lint` caches via pip keyed on `requirements-lint.txt`.
- `lock-freshness` is a new status check; maintainers may want to add it to required checks post-merge.
- `auto-deps.yml` now regenerates the lock after security fixes; on lock-regen failure the PR is still opened with a warning.
- `auto-lint.yml` stays on latest `ruff`, no cache.
- `requirements-dev.txt` removed.

- [ ] **Step 9: Final commit if anything changed during verification**

If any verification step surfaced a fix, commit it:

```bash
git add -p
git commit -m "ci: verification follow-ups from end-to-end check

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

If nothing changed, this step is a no-op.

---

## Rollback

Each task is a single self-contained commit. To revert:

- Any individual task: `git revert <commit-sha>`
- All work: `git revert <first-commit>..<last-commit>` (inclusive range).

After a revert, `make lock-check` will fail if the revert undid the lock file or the Makefile targets. Running `make lock` (if `uv` is installed) will restore a compatible state; otherwise revert `Makefile` and `requirements-test.lock` together.
