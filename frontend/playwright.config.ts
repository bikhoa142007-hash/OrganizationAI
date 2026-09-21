import { defineConfig } from '@playwright/test'
import { resolve } from 'node:path'

const root = resolve(import.meta.dirname, '..')
const python = process.platform === 'win32' ? '.venv\\Scripts\\python.exe' : '.venv/bin/python'
const database = `runtime/demo-e2e-${Date.now()}.sqlite3`
export default defineConfig({
  testDir: './e2e', workers: 1, timeout: 45000, retries: 0,
  use: { baseURL: 'http://127.0.0.1:5178', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  webServer: [
    { command: `${python} -m src.backend.seed_demo && ${python} -m uvicorn src.backend.api.app:app --host 127.0.0.1 --port 8008`, cwd: root,
      env: { APP_ENV: 'demo', DEMO_DATABASE: database, CORS_ORIGINS: 'http://127.0.0.1:5178' }, url: 'http://127.0.0.1:8008/api/health', reuseExistingServer: false },
    { command: 'npm run dev -- --host 127.0.0.1 --port 5178 --strictPort',
      env: { VITE_API_BASE_URL: 'http://127.0.0.1:8008/api' }, url: 'http://127.0.0.1:5178', reuseExistingServer: false },
  ],
})
