import { afterEach, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from '../context/AuthContext'
import { AuthenticatedWorkflowFormPage } from '../pages/AuthenticatedWorkflowFormPage'
import { api } from './api/client'
import { authService } from './auth'
import { authWorkflowService } from './authWorkflow'
import { SessionProvider, useSession } from './SessionProvider'

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

it('sends authenticated workflow requests with cookies and without a demo actor header', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response('[]', { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)

  await expect(authWorkflowService.listPlans()).resolves.toEqual([])

  const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit]
  expect(url).toContain('/workflow/plans')
  expect(options.credentials).toBe('include')
  expect(options.headers).toBeUndefined()
  expect(JSON.stringify(options)).not.toContain('X-Demo-Actor')
})

it('loads the Auth session on authenticated workflow routes', async () => {
  vi.spyOn(authService, 'me').mockResolvedValue({
    id: 'maker-id', user_code: 'USR-1', username: 'maker', email: 'maker@example.com',
    phone: null, display_name: 'Maker One', status: 'ACTIVE', roles: ['MAKER'],
  })
  function AuthProbe() {
    const { user, isLoading } = useAuth()
    return <p>{isLoading ? 'auth-loading' : user?.display_name}</p>
  }
  render(<MemoryRouter initialEntries={['/workflow/plans']}><AuthProvider><AuthProbe /></AuthProvider></MemoryRouter>)

  expect(await screen.findByText('Maker One')).toBeVisible()
})

it('does not resolve a PostgreSQL Auth cookie through the Judge Demo session', async () => {
  const demoRequest = vi.spyOn(api, 'request')
  function DemoProbe() {
    const { config, loading } = useSession()
    return <p>{loading ? 'session-loading' : config ? 'demo-session' : 'auth-only-session'}</p>
  }
  render(<MemoryRouter initialEntries={['/workflow/plans']}><SessionProvider><DemoProbe /></SessionProvider></MemoryRouter>)

  expect(await screen.findByText('auth-only-session')).toBeVisible()
  await waitFor(() => expect(demoRequest).not.toHaveBeenCalled())
})

it('does not turn a failed edit-page load into a create form', async () => {
  vi.spyOn(authWorkflowService, 'listCheckers').mockResolvedValue([])
  vi.spyOn(authWorkflowService, 'getPlan').mockRejectedValue(new Error('Forbidden'))
  const createPlan = vi.spyOn(authWorkflowService, 'createPlan')

  render(
    <MemoryRouter initialEntries={['/workflow/plans/plan-private/edit']}>
      <Routes><Route path="/workflow/plans/:planId/edit" element={<AuthenticatedWorkflowFormPage />} /></Routes>
    </MemoryRouter>,
  )

  expect(await screen.findByRole('alert')).toHaveTextContent('Không thể tải kế hoạch')
  expect(screen.queryByRole('heading', { name: 'Tạo kế hoạch marketing' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Lưu bản nháp' })).not.toBeInTheDocument()
  expect(createPlan).not.toHaveBeenCalled()
})
