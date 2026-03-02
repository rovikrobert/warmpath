import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  retries: 0,
  use: {
    baseURL: 'http://127.0.0.1:4173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 4173',
    cwd: '.',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: true,
    env: {
      VITE_E2E_SMOKE_ROUTE: 'true',
      VITE_E2E_BYPASS_AUTH: 'true',
      VITE_CLERK_PUBLISHABLE_KEY: '[CLERK_KEY_REDACTED]',
    },
  },
});
