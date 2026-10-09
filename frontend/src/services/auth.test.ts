import { afterEach, expect, it, vi } from 'vitest'
import { AuthApiError, authService } from './auth'

const user = {
  id: 'user-1', user_code: 'USR-000001', username: 'maker', email: null,
  phone: '+84901234567', display_name: 'maker', status: 'ACTIVE', roles: ['MAKER'],
}

afterEach(() => vi.unstubAllGlobals())

it('logs in with an HttpOnly-cookie session request and never sends the demo actor header', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ user }), {
    status: 200, headers: { 'Content-Type': 'application/json' },
  }))
  vi.stubGlobal('fetch', fetchMock)

  await authService.login('maker', 'local-secret', true)

  const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit]
  expect(url).toContain('/auth/login')
  expect(options.credentials).toBe('include')
  expect(JSON.parse(String(options.body))).toEqual({
    identifier: 'maker', password: 'local-secret', remember_me: true,
  })
  expect(new Headers(options.headers).has('X-Demo-Actor')).toBe(false)
  expect(new Headers(options.headers).has('Authorization')).toBe(false)
})

it('registers through the authentication API without accepting a client role', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ user }), {
    status: 201, headers: { 'Content-Type': 'application/json' },
  }))
  vi.stubGlobal('fetch', fetchMock)

  await authService.register('maker', '+84 (90) 123-4567', 'local-secret')

  const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit]
  expect(url).toContain('/auth/register')
  expect(options.credentials).toBe('include')
  expect(JSON.parse(String(options.body))).toEqual({
    username: 'maker', contact: '+84 (90) 123-4567', password: 'local-secret',
  })
})

it('refreshes the session from the backend rather than a client-side flag', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ user }), {
    status: 200, headers: { 'Content-Type': 'application/json' },
  }))
  vi.stubGlobal('fetch', fetchMock)

  const currentUser = await authService.me()

  expect(currentUser).toEqual(user)
  expect(fetchMock.mock.calls[0][0]).toContain('/auth/me')
  expect((fetchMock.mock.calls[0][1] as RequestInit).credentials).toBe('include')
})

it('reads only the server registration feature switch', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ registration_enabled: false }), {
    status: 200, headers: { 'Content-Type': 'application/json' },
  }))
  vi.stubGlobal('fetch', fetchMock)

  await expect(authService.getRegistrationConfig()).resolves.toEqual({ registration_enabled: false })
  expect(fetchMock.mock.calls[0][0]).toContain('/auth/config')
  expect((fetchMock.mock.calls[0][1] as RequestInit).credentials).toBe('include')
})

it('parses the API error envelope without losing status, code, message, or correlation id', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
    code: 'CONFLICT', message: 'The account already exists.', correlation_id: 'auth-trace-42', http_status: 409,
  }), { status: 409, headers: { 'Content-Type': 'application/json' } }))
  vi.stubGlobal('fetch', fetchMock)

  const failure = await authService.register('maker', 'maker@example.com', 'a sufficiently long password')
    .catch(error => error)

  expect(failure).toBeInstanceOf(AuthApiError)
  expect(failure).toMatchObject({
    status: 409, code: 'CONFLICT', message: 'The account already exists.',
    correlationId: 'auth-trace-42', correlation_id: 'auth-trace-42',
  })
})

it('sends logout with the cookie session and resolves only for HTTP 204', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
  vi.stubGlobal('fetch', fetchMock)

  await expect(authService.logout()).resolves.toBeUndefined()

  const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit]
  expect(url).toContain('/auth/logout')
  expect(options.method).toBe('POST')
  expect(options.credentials).toBe('include')
  expect(options.body).toBeUndefined()
})

it('rejects a successful non-204 logout response', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)

  await expect(authService.logout()).rejects.toMatchObject({ status: 200, code: 'UNEXPECTED_STATUS' })
})

it('marks a failed fetch as a network error with no fabricated HTTP status', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))

  await expect(authService.me()).rejects.toMatchObject({ status: 0, code: 'NETWORK_ERROR' })
})
