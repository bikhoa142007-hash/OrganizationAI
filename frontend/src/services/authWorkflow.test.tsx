import { afterEach, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from '../context/AuthContext'
import { AuthenticatedWorkflowFormPage } from '../pages/AuthenticatedWorkflowFormPage'
import { api } from './api/client'
import { authService } from './auth'
import { authWorkflowService } from './authWorkflow'
import type { WorkflowPayload } from '../types/authWorkflow'
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

it('uses an explicit authenticated POST for stale evaluation recovery', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)

  await authWorkflowService.recoverStaleEvaluation('plan/1', 2)

  const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit]
  expect(url).toContain('/workflow/plans/plan%2F1/rounds/2/recovery')
  expect(options.method).toBe('POST')
  expect(options.credentials).toBe('include')
  expect(options.body).toBeUndefined()
})

it('reuses a draft creation key after a network error and rotates it after success', async () => {
  const fetchMock = vi.fn()
    .mockRejectedValueOnce(new TypeError('offline'))
    .mockResolvedValueOnce(new Response('{}', { status: 201 }))
    .mockResolvedValueOnce(new Response('{}', { status: 201 }))
  vi.stubGlobal('fetch', fetchMock)
  const payload: WorkflowPayload = {
    title: 'Retry-safe draft', objective: '', summary: '', department: '',
    start_date: '', end_date: '', budget_minor_units: '', currency: 'VND',
    target_audience: '', channels: [], kpi_expected: '', notes: '',
  }

  await expect(authWorkflowService.createPlan(payload, null)).rejects.toMatchObject({ status: 0 })
  await authWorkflowService.createPlan(payload, null)
  await authWorkflowService.createPlan(payload, null)

  const keys = fetchMock.mock.calls.map(([, options]) => (options as RequestInit).headers as Record<string, string>)
    .map(headers => headers['Idempotency-Key'])
  expect(keys[0]).toBeTruthy()
  expect(keys[1]).toBe(keys[0])
  expect(keys[2]).toBeTruthy()
  expect(keys[2]).not.toBe(keys[1])
})

it('distinguishes an expired session from an authenticated authorization denial', async () => {
  const expired = vi.fn()
  const denied = vi.fn()
  window.addEventListener('organizationai:auth-expired', expired)
  window.addEventListener('organizationai:access-denied', denied)
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce(new Response('{}', { status: 401 }))
    .mockResolvedValueOnce(new Response('{}', { status: 403 })))

  await expect(authWorkflowService.listPlans()).rejects.toMatchObject({ status: 401 })
  await expect(authWorkflowService.listPlans()).rejects.toMatchObject({ status: 403 })
  expect(expired).toHaveBeenCalledTimes(1)
  expect(denied).toHaveBeenCalledTimes(1)
  window.removeEventListener('organizationai:auth-expired', expired)
  window.removeEventListener('organizationai:access-denied', denied)
})

it('distinguishes an expired session from an authenticated authorization denial', async () => {
  const expired = vi.fn()
  const denied = vi.fn()
  window.addEventListener('organizationai:auth-expired', expired)
  window.addEventListener('organizationai:access-denied', denied)
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce(new Response('{}', { status: 401 }))
    .mockResolvedValueOnce(new Response('{}', { status: 403 })))

  await expect(authWorkflowService.listPlans()).rejects.toMatchObject({ status: 401 })
  await expect(authWorkflowService.listPlans()).rejects.toMatchObject({ status: 403 })
  expect(expired).toHaveBeenCalledTimes(1)
  expect(denied).toHaveBeenCalledTimes(1)
  window.removeEventListener('organizationai:auth-expired', expired)
  window.removeEventListener('organizationai:access-denied', denied)
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
