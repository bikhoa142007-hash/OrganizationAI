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

function apiPath(url: string) {
  const parsed = new URL(url)
  return `${parsed.pathname.replace(/^\/api(?=\/)/, '')}${parsed.search}`
}

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

it('lists validated employee pages with encoded filters and cookie authentication', async () => {
  const employeePage = {
    items: [{
      id: 'employee-1', account_id: 'user-1', user_code: 'USR-0001', username: 'maker.one',
      display_name: 'Maker One', email: 'maker@example.com', phone: null,
      department: 'Marketing', job_title: 'Planner', employment_start_date: '2022-04-15',
      employment_status: 'ACTIVE', status: 'ACTIVE', account_status: 'ACTIVE', roles: ['MAKER'], effective_permissions: [],
    }],
    offset: 25, limit: 25, total: 26,
  }
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(employeePage), { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)

  await expect(authWorkflowService.listEmployees({
    query: 'Maker & Plan', role: 'MAKER', status: 'ACTIVE', department: 'Marketing',
    job_title: 'Planner', employment_status: 'ACTIVE', offset: 25, limit: 25,
  })).resolves.toEqual(employeePage)

  const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit]
  const parsed = new URL(url)
  expect(parsed.pathname).toContain('/workflow/employees')
  expect(parsed.searchParams.get('query')).toBe('Maker & Plan')
  expect(parsed.searchParams.get('role')).toBe('MAKER')
  expect(parsed.searchParams.get('status')).toBe('ACTIVE')
  expect(parsed.searchParams.get('department')).toBe('Marketing')
  expect(parsed.searchParams.get('job_title')).toBe('Planner')
  expect(parsed.searchParams.get('employment_status')).toBe('ACTIVE')
  expect(parsed.searchParams.get('offset')).toBe('25')
  expect(options.method).toBe('GET')
  expect(options.credentials).toBe('include')
  expect(options.body).toBeUndefined()
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

it('reuses a draft creation key for a retry and rotates it for a new intent', async () => {
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

  await expect(authWorkflowService.createPlan(payload, null, 'retry-intent')).rejects.toMatchObject({ status: 0 })
  await authWorkflowService.createPlan(payload, null, 'retry-intent')
  await authWorkflowService.createPlan(payload, null, 'new-intent')

  const keys = fetchMock.mock.calls.map(([, options]) => (options as RequestInit).headers as Record<string, string>)
    .map(headers => headers['Idempotency-Key'])
  expect(keys[0]).toBeTruthy()
  expect(keys[1]).toBe(keys[0])
  expect(keys[2]).toBeTruthy()
  expect(keys[2]).not.toBe(keys[1])
})

it('replays a server-created draft after a reload and isolates separate intents', async () => {
  const server = new Map<string, { body: string; plan: { id: string } }>()
  const observedKeys: string[] = []
  let created = 0
  let dropFirstResponse = true
  const fetchMock = vi.fn(async (_url: string, options: RequestInit) => {
    const key = (options.headers as Record<string, string>)['Idempotency-Key']
    const body = String(options.body)
    observedKeys.push(key)
    const prior = server.get(key)
    if (prior) {
      if (prior.body !== body) return new Response('{}', { status: 409 })
      return new Response(JSON.stringify(prior.plan), { status: 201 })
    }

    const plan = { id: `server-plan-${++created}` }
    server.set(key, { body, plan })
    if (dropFirstResponse) {
      dropFirstResponse = false
      throw new TypeError('response lost after commit')
    }
    return new Response(JSON.stringify(plan), { status: 201 })
  })
  vi.stubGlobal('fetch', fetchMock)
  const payload: WorkflowPayload = {
    title: 'Reload-safe draft', objective: '', summary: '', department: '',
    start_date: '', end_date: '', budget_minor_units: '', currency: 'VND',
    target_audience: '', channels: [], kpi_expected: '', notes: '',
  }

  await expect(authWorkflowService.createPlan(payload, null, 'intent-one')).rejects.toMatchObject({ status: 0 })
  vi.resetModules()
  const { authWorkflowService: reloadedService } = await import('./authWorkflow')
  await expect(reloadedService.createPlan(payload, null, 'intent-one')).resolves.toEqual({ id: 'server-plan-1' })
  await expect(reloadedService.createPlan(payload, null, 'intent-two')).resolves.toEqual({ id: 'server-plan-2' })
  await expect(reloadedService.createPlan({ ...payload, title: 'Changed request' }, null, 'intent-one'))
    .rejects.toMatchObject({ status: 409 })

  expect(created).toBe(2)
  expect(observedKeys[1]).toBe(observedKeys[0])
  expect(observedKeys[2]).not.toBe(observedKeys[1])
  expect(observedKeys[3]).toBe(observedKeys[0])
})

it('distinguishes an expired session from an authenticated authorization denial', async () => {
  const expired = vi.fn()
  const denied = vi.fn()
  window.addEventListener('organizationai:auth-expired', expired)
  window.addEventListener('organizationai:access-denied', denied)
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ code: 'UNAUTHENTICATED', message: 'Sign in again.', correlation_id: 'trace-401' }), { status: 401 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ code: 'FORBIDDEN', message: 'Not allowed.', correlation_id: 'trace-403' }), { status: 403 })))

  await expect(authWorkflowService.listPlans()).rejects.toMatchObject({ status: 401, code: 'UNAUTHENTICATED', message: 'Sign in again.', correlationId: 'trace-401' })
  await expect(authWorkflowService.listPlans()).rejects.toMatchObject({ status: 403, code: 'FORBIDDEN', message: 'Not allowed.', correlationId: 'trace-403' })
  expect(expired).toHaveBeenCalledTimes(1)
  expect(denied).toHaveBeenCalledTimes(1)
  window.removeEventListener('organizationai:auth-expired', expired)
  window.removeEventListener('organizationai:access-denied', denied)
})

it('reads the current Checker list and request detail from the existing API routes', async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response('[{"id":"checker-1","display_name":"Checker One"}]', { status: 200 }))
    .mockResolvedValueOnce(new Response('{"id":"plan-1","code":"MKT-1"}', { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)
  await expect(authWorkflowService.listCheckers()).resolves.toEqual([{ id: 'checker-1', display_name: 'Checker One' }])
  await expect(authWorkflowService.getPlan('plan/one')).resolves.toMatchObject({ id: 'plan-1' })

  expect(fetchMock.mock.calls.map(([url, options]) => [
    apiPath(url as string), (options as RequestInit).method,
    (options as RequestInit).credentials,
  ])).toEqual([
    ['/workflow/checkers', 'GET', 'include'],
    ['/workflow/plans/plan%2Fone', 'GET', 'include'],
  ])
})

it('requests Checker review pages with the backend offset and limit contract', async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response('[{"id":"plan-1"}]', { status: 200 }))
    .mockResolvedValueOnce(new Response('[]', { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)

  await expect(authWorkflowService.listReviews(0, 100)).resolves.toMatchObject([{ id: 'plan-1' }])
  await expect(authWorkflowService.listReviews(100, 100)).resolves.toEqual([])

  expect(fetchMock.mock.calls.map(([url, options]) => [
    apiPath(url as string),
    (options as RequestInit).method,
    (options as RequestInit).credentials,
  ])).toEqual([
    ['/workflow/reviews?offset=0&limit=100', 'GET', 'include'],
    ['/workflow/reviews?offset=100&limit=100', 'GET', 'include'],
  ])
})

it('requests Maker pages with only the backend offset and limit contract', async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response('[]', { status: 200 }))
    .mockResolvedValueOnce(new Response('[]', { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)

  await expect(authWorkflowService.listPlans(0, 100)).resolves.toEqual([])
  await expect(authWorkflowService.listPlans(100, 100)).resolves.toEqual([])

  expect(fetchMock.mock.calls.map(([url, options]) => [
    apiPath(url as string),
    (options as RequestInit).method,
    (options as RequestInit).credentials,
  ])).toEqual([
    ['/workflow/plans?offset=0&limit=100', 'GET', 'include'],
    ['/workflow/plans?offset=100&limit=100', 'GET', 'include'],
  ])
})

it('rejects a malformed workflow plan list response without inventing records', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"items":[]}', { status: 200 })))

  await expect(authWorkflowService.listPlans(0, 100))
    .rejects.toMatchObject({ status: 200, code: 'INVALID_RESPONSE' })
})

it('posts Checker decisions to the existing round-scoped endpoint with its contract body', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response('{"id":"plan-1","status":"APPROVED"}', { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)

  await expect(authWorkflowService.decide('plan/one', 3, 'APPROVED', '', 'Reviewed manually.'))
    .resolves.toMatchObject({ id: 'plan-1', status: 'APPROVED' })

  const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit]
  expect(apiPath(url)).toBe('/workflow/plans/plan%2Fone/rounds/3/decision')
  expect(options.method).toBe('POST')
  expect(options.credentials).toBe('include')
  expect(JSON.parse(options.body as string)).toEqual({ action: 'APPROVED', reason: '', override_reason: 'Reviewed manually.' })
})

it.each([401, 403, 404, 409, 422, 503])('retains decision error status, code, message and correlation ID for HTTP %s', async status => {
  const code = ({ 401: 'UNAUTHENTICATED', 403: 'FORBIDDEN', 404: 'NOT_FOUND', 409: 'CONFLICT', 422: 'VALIDATION_ERROR', 503: 'SERVICE_UNAVAILABLE' } as Record<number, string>)[status]
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
    code, message: 'Decision was not accepted.', correlation_id: `decision-trace-${status}`, http_status: status,
  }), { status })))

  await expect(authWorkflowService.decide('plan-1', 4, 'REJECTED', 'Reason', 'Override'))
    .rejects.toMatchObject({ status, code, message: 'Decision was not accepted.', correlationId: `decision-trace-${status}` })
})

it('sends create, update and submit to the existing workflow endpoints with contract bodies', async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response('{"id":"p1"}', { status: 201 }))
    .mockResolvedValueOnce(new Response('{"id":"p1"}', { status: 200 }))
    .mockResolvedValueOnce(new Response('{"id":"p1"}', { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)
  const payload = {
    title: 'Campaign', objective: 'Reach customers', summary: 'Summary', department: 'Marketing',
    start_date: '2026-10-01', end_date: '2026-10-31', budget_minor_units: '250000', currency: 'VND',
    target_audience: '', channels: ['Email'], kpi_expected: '', notes: '',
  }

  await authWorkflowService.createPlan(payload, 'checker-1', 'contract-test-intent')
  await authWorkflowService.updatePlan('plan/one', payload, null, 4)
  await authWorkflowService.submitPlan('plan/one', 5)

  expect(fetchMock.mock.calls.map(([url, options]) => [apiPath(url as string), (options as RequestInit).method])).toEqual([
    ['/workflow/plans', 'POST'], ['/workflow/plans/plan%2Fone', 'PUT'], ['/workflow/plans/plan%2Fone/submit', 'POST'],
  ])
  expect(JSON.parse((fetchMock.mock.calls[0]?.[1] as RequestInit).body as string)).toEqual({ payload, checker_user_id: 'checker-1' })
  expect(JSON.parse((fetchMock.mock.calls[1]?.[1] as RequestInit).body as string)).toEqual({ payload, checker_user_id: null, expected_revision: 4 })
  expect(JSON.parse((fetchMock.mock.calls[2]?.[1] as RequestInit).body as string)).toEqual({ expected_revision: 5 })
  expect(fetchMock.mock.calls.every(([, options]) => (options as RequestInit).credentials === 'include')).toBe(true)
})

it('uploads multipart attachments and downloads private attachment bytes through backend routes', async () => {
  const attachmentBytes = new TextEncoder().encode('image-bytes')
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response('{"id":"p1"}', { status: 200 }))
    .mockResolvedValueOnce(new Response(attachmentBytes, { status: 200, headers: { 'Content-Type': 'image/png' } }))
  vi.stubGlobal('fetch', fetchMock)
  const file = new File(['pixels'], 'campaign.png', { type: 'image/png' })

  await authWorkflowService.uploadAttachment('plan-1', file, 7)
  const uploadedOptions = fetchMock.mock.calls[0]?.[1] as RequestInit
  expect(fetchMock.mock.calls[0]?.[0]).toContain('/workflow/plans/plan-1/attachments')
  expect(uploadedOptions.credentials).toBe('include')
  expect(uploadedOptions.headers).toBeUndefined()
  expect(uploadedOptions.body).toBeInstanceOf(FormData)
  expect((uploadedOptions.body as FormData).get('file')).toBe(file)
  expect((uploadedOptions.body as FormData).get('expected_revision')).toBe('7')

  const downloadedAttachment = await authWorkflowService.getAttachment('plan-1', 'attachment-1')
  expect(downloadedAttachment.type).toBe('image/png')
  expect(downloadedAttachment.size).toBe(attachmentBytes.byteLength)
  expect(Array.from(new Uint8Array(await downloadedAttachment.arrayBuffer())))
    .toEqual(Array.from(attachmentBytes))
  expect(fetchMock.mock.calls[1]?.[0]).toContain('/workflow/plans/plan-1/attachments/attachment-1')
  const downloadOptions = fetchMock.mock.calls[1]?.[1] as RequestInit
  expect(downloadOptions.credentials).toBe('include')
  expect(downloadOptions.headers).toBeUndefined()
})

it.each([404, 409, 422, 503])('retains workflow API error fields and header correlation ID for HTTP %s', async status => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
    code: status === 409 ? 'CONFLICT' : status === 422 ? 'VALIDATION_ERROR' : `HTTP_${status}`,
    message: 'Request could not be completed.',
    correlation_id: status === 404 ? '' : `trace-${status}`,
    http_status: status,
  }), { status, headers: { 'X-Correlation-ID': 'trace-header' } })))

  await expect(authWorkflowService.listPlans()).rejects.toMatchObject({
    status,
    code: status === 409 ? 'CONFLICT' : status === 422 ? 'VALIDATION_ERROR' : `HTTP_${status}`,
    message: 'Request could not be completed.',
    correlationId: status === 404 ? 'trace-header' : `trace-${status}`,
  })
})

it('uses a network error code when an authenticated workflow request cannot connect', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
  await expect(authWorkflowService.listPlans()).rejects.toMatchObject({ status: 0, code: 'NETWORK_ERROR' })
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

  expect(await screen.findByRole('alert')).toHaveTextContent('Không thể hoàn tất yêu cầu')
  expect(screen.queryByRole('heading', { name: 'Tạo kế hoạch marketing' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Lưu bản nháp' })).not.toBeInTheDocument()
  expect(createPlan).not.toHaveBeenCalled()
})
