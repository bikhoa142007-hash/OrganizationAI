import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { App } from './App'
import { authService } from './services/auth'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllEnvs()
})

it('does not initialize Auth for deep links in a Public Judge-only build', async () => {
  vi.stubEnv('VITE_PUBLIC_JUDGE_ONLY', 'true')
  vi.stubEnv('VITE_DEMO_ENABLED', 'true')
  window.history.replaceState({}, '', '/workflow/plans/new')
  const loadPrincipal = vi.spyOn(authService, 'me')

  render(<App />)

  expect(await screen.findByRole('heading', { name: 'Verify workflow' })).toBeVisible()
  expect(screen.getByText('Judge công khai, không cần tạo tài khoản')).toBeVisible()
  expect(loadPrincipal).not.toHaveBeenCalled()
})
