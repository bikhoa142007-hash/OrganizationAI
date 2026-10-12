import { defineConfig } from '@playwright/test'

const port = process.env.PUBLICATION_E2E_VITE_PORT ?? '5190'
const apiBase = process.env.VITE_API_BASE_URL
if (!apiBase) throw new Error('Set VITE_API_BASE_URL to the isolated PostgreSQL Auth API.')

export default defineConfig({
  testDir: './e2e',
  testMatch: ['auth-live.spec.ts', 'sla-live.spec.ts', 'publication-integrated-live.spec.ts'],
  workers: 1,
  timeout: 600_000,
  expect: { timeout: 30_000 },
  retries: 0,
  reporter: 'list',
  outputDir: process.env.PLAYWRIGHT_OUTPUT_DIR ?? 'test-results',
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    headless: true,
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
  webServer: {
    command: `npm run dev -- --host 127.0.0.1 --port ${port} --strictPort`,
    url: `http://127.0.0.1:${port}`,
    reuseExistingServer: false,
    env: { VITE_API_BASE_URL: apiBase, VITE_DEMO_ENABLED: 'false' },
    timeout: 60_000,
  },
})
