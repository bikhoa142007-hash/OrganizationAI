import { defineConfig } from '@playwright/test'

const baseURL = process.env.AUTH_E2E_BASE_URL ?? 'http://localhost:5173'

export default defineConfig({
  testDir: './e2e',
  testMatch: 'auth-live.spec.ts',
  workers: 1,
  timeout: 600_000,
  expect: { timeout: 30_000 },
  retries: 0,
  reporter: 'list',
  use: {
    baseURL,
    headless: true,
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
})
