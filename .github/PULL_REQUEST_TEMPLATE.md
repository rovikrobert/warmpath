<!--
  WarmPath was sunset on April 28, 2026.
  Pull requests against this repository are NOT reviewed or merged.

  Please fork the project and maintain your own line. The template below
  is provided so forks can adopt a consistent PR format if they choose.
-->

## Summary

<!-- What does this change do, and why? -->

## Test plan

- [ ] `pytest -m smoke -q` passes
- [ ] `pytest -n auto --timeout=120` passes (or relevant subset)
- [ ] `ruff format --check . && ruff check .` passes
- [ ] Frontend (if touched): `cd frontend && npm run lint && npm run build`
- [ ] Manual verification of the user-visible change

## Notes for fork maintainers

- License: contributions assumed Apache-2.0 (see [LICENSE](../LICENSE)).
- Conduct: see [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md).
