import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  testMatch: 'auth-live.spec.ts',
  workers: 1,
  timeout: 600_000,
  expect: { timeout: 30_000 },
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:5173',
    headless: true,
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
})
