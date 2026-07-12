import { defineConfig } from '@playwright/test';

// Smoke tests for the built site (issue #43). `pnpm build` must have run
// first — preview serves dist/ as-is, which is exactly what Pages deploys,
// so the tests exercise the same artifact users get (base path /scm
// included).
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: 'http://localhost:4321',
  },
  webServer: {
    command: 'npm run preview',
    url: 'http://localhost:4321/scm/',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
