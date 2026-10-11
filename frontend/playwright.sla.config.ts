import { defineConfig } from '@playwright/test'

const apiBase = process.env.VITE_API_BASE_URL
if (!apiBase) throw new Error('Set VITE_API_BASE_URL to the isolated temporary SLA API.')
const port = process.env.SLA_E2E_VITE_PORT ?? '5180'
const testMatch = process.env.SLA_E2E_TEST_MATCH ?? 'sla-live.spec.ts'

export default defineConfig({
  testDir: './e2e',
  testMatch,
  workers: 1,
  timeout: 180_000,
  expect: { timeout: 20_000 },
  retries: 0,
  reporter: 'list',
  outputDir: process.env.PLAYWRIGHT_OUTPUT_DIR ?? 'test-results',
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: `npm run dev -- --host 127.0.0.1 --port ${port} --strictPort`,
    url: `http://127.0.0.1:${port}`,
    reuseExistingServer: false,
    env: {
      VITE_API_BASE_URL: apiBase,
      VITE_DEMO_ENABLED: process.env.VITE_DEMO_ENABLED ?? 'false',
    },
    timeout: 60_000,
  },
})
