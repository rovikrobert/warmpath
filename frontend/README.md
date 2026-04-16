# WarmPath frontend

React 19 + Vite 7 + TypeScript + Tailwind CSS 4. Routed via
`react-router-dom`, auth via Clerk, UI primitives from Radix +
[shadcn/ui](https://ui.shadcn.com/) (see `components.json`).

> Project status: **sunset April 28, 2026.** See the
> [root README](../README.md) for context. PRs/issues are not reviewed.

## Setup

```bash
# from repo root, the easy path:
make dev                      # brings up frontend in Docker on :5173

# or run the dev server directly against a local API:
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

The Vite dev server proxies API calls; configure auth in
[`.env.dev`](../.env.dev.example) (`VITE_CLERK_PUBLISHABLE_KEY`,
`VITE_API_URL`, `VITE_BETA_MODE`).

## Scripts

| Command | What it does |
| --- | --- |
| `npm run dev` | Vite dev server with HMR |
| `npm run build` | Production build to `dist/` (served by FastAPI in prod) |
| `npm run preview` | Preview the built bundle |
| `npm run lint` | ESLint over `src/` |
| `npm run test:e2e` | Playwright end-to-end tests (headless) |
| `npm run test:e2e:headed` | Playwright with a visible browser |
| `npm run build:analyze` | Bundle size visualizer |

## Layout

```
src/         application code (pages, components, hooks, lib)
public/      static assets served as-is
e2e/         Playwright specs
scripts/     local utility scripts
```

## License

Apache-2.0, same as the rest of the repo. See [LICENSE](../LICENSE) and
[NOTICE](../NOTICE).
